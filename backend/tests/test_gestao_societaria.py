"""Gestão societária do PRÓPRIO escritório — /sociedade/socios.

Sem Postgres real (padrão test_sociedades_cliente.py): handlers chamados
diretamente com fake de sessão. Cobre a correção SOC-01 (achado de auditoria):

  - PATCH /sociedade/socios/{id} exigia apenas nível `socio` (7) para alterar
    participação/pró-labore, nível MENOR que o exigido para cadastrar um sócio
    novo (`admin`, 8) — inversão de risco;
  - o PATCH não deixava trilha de auditoria.

Não confundir com `sociedades_cliente.py` (gestão societária de empresas de
CLIENTES) — módulo diferente, não tocado aqui.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.socio import RegimeSocio, Socio
from app.models.user import User, UserRole
from app.routers.gestao_societaria import (
    SocioIn, SocioPatch,
    atualizar_socio, cadastrar_socio, aprovar_distribuicao, calcular_distribuicao,
)
from app.models.socio import DistribuicaoLucro


# ── Fakes (sem banco, padrão test_sociedades_cliente.py) ──────────────────────

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalar(self):
        return self._val


class _FakeDB:
    """Sessão fake: fila de resultados para execute(); registra add()/commit()."""

    def __init__(self, resultados: list):
        self._resultados = list(resultados)
        self.added: list = []
        self.commits = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass

    async def refresh(self, obj):
        pass


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


def _socio(**kw) -> Socio:
    base = dict(
        id="socio1", user_id="dono", participacao_percentual=Decimal("0.5000"),
        regime=RegimeSocio.misto, pro_labore=Decimal("10000.00"),
        oab_numero=None, oab_uf=None, data_entrada=date(2020, 1, 1),
        data_saida=None, ativo=True, observacoes=None,
    )
    base.update(kw)
    return Socio(**base)


# ── PATCH /sociedade/socios/{id}: nível de permissão (SOC-01) ─────────────────

async def test_socio_nivel_socio_nao_pode_alterar_participacao():
    """Sócio (nível 7) tentando alterar a própria participação recebe 403 —
    o mesmo nível exigido para CADASTRAR um sócio (admin, nível 8)."""
    db = _FakeDB([])  # não deve nem chegar a consultar o sócio
    with pytest.raises(HTTPException) as exc:
        await atualizar_socio(
            socio_id="socio1",
            req=SocioPatch(participacao_percentual=0.9),
            db=db, cu=_user(UserRole.socio),
        )
    assert exc.value.status_code == 403
    assert db.commits == 0
    assert db.added == []


async def test_advogado_nao_pode_alterar_socio():
    db = _FakeDB([])
    with pytest.raises(HTTPException) as exc:
        await atualizar_socio(
            socio_id="socio1",
            req=SocioPatch(pro_labore=99999),
            db=db, cu=_user(UserRole.advogado),
        )
    assert exc.value.status_code == 403


async def test_admin_pode_alterar_socio_e_gera_auditoria():
    """Admin (nível 8) altera participação/pró-labore com sucesso e a
    alteração fica registrada em AuditLog com dados_antes/dados_depois,
    na mesma transação (um único commit)."""
    s = _socio()
    db = _FakeDB([s])
    out = await atualizar_socio(
        socio_id="socio1",
        req=SocioPatch(participacao_percentual=0.6, pro_labore=15000),
        db=db, cu=_user(UserRole.admin, "admin1"),
    )
    assert out["participacao_percentual"] == 0.6
    assert out["pro_labore"] == 15000.0

    logs = [o for o in db.added if isinstance(o, AuditLog)]
    assert len(logs) == 1
    log = logs[0]
    assert log.acao == "UPDATE"
    assert log.entidade == "socios"
    assert log.registro_id == "socio1"
    assert log.user_id == "admin1"
    assert log.dados_antes["participacao_percentual"] == 0.5
    assert log.dados_antes["pro_labore"] == 10000.0
    assert log.dados_depois["participacao_percentual"] == 0.6
    assert log.dados_depois["pro_labore"] == 15000.0

    # Auditoria e alteração commitam juntas — não há commit da alteração sem
    # o registro de auditoria já adicionado à sessão.
    assert db.commits == 1


async def test_superadmin_pode_alterar_socio():
    s = _socio()
    db = _FakeDB([s])
    out = await atualizar_socio(
        socio_id="socio1",
        req=SocioPatch(observacoes="revisado"),
        db=db, cu=_user(UserRole.superadmin, "root1"),
    )
    assert out["observacoes"] == "revisado"
    assert db.commits == 1


async def test_auditoria_reflete_campos_realmente_alterados():
    """PATCH que só troca `regime` e `ativo` tem que gravar ESSES campos no
    snapshot de auditoria — não participação/pró-labore inalterados (achado
    de review em PR #1071: snapshot fixo escondia a real mudança feita)."""
    s = _socio()
    db = _FakeDB([s])
    await atualizar_socio(
        socio_id="socio1",
        req=SocioPatch(regime=RegimeSocio.resultado, ativo=False),
        db=db, cu=_user(UserRole.admin, "admin1"),
    )
    logs = [o for o in db.added if isinstance(o, AuditLog)]
    assert len(logs) == 1
    log = logs[0]
    assert set(log.dados_antes) == {"regime", "ativo"}
    assert set(log.dados_depois) == {"regime", "ativo"}
    assert log.dados_antes == {"regime": "misto", "ativo": True}
    assert log.dados_depois == {"regime": "resultado", "ativo": False}
    # participação/pró-labore nem entram no snapshot — não foram tocados
    assert "participacao_percentual" not in log.dados_antes
    assert "pro_labore" not in log.dados_antes


async def test_auditoria_campo_sem_valor_previo_nao_quebra():
    """`meta_produtividade` não é coluna mapeada no model `Socio` (só existe
    em runtime se algum PATCH anterior no mesmo processo já a setou como
    atributo Python solto) — o snapshot não pode estourar AttributeError na
    primeira vez que o campo é alterado."""
    s = _socio()
    db = _FakeDB([s])
    out = await atualizar_socio(
        socio_id="socio1",
        req=SocioPatch(meta_produtividade=5000.0),
        db=db, cu=_user(UserRole.admin, "admin1"),
    )
    assert out["meta_produtividade"] == 5000.0
    logs = [o for o in db.added if isinstance(o, AuditLog)]
    assert logs[0].dados_antes == {"meta_produtividade": None}
    assert logs[0].dados_depois == {"meta_produtividade": 5000.0}


async def test_socio_inexistente_404():
    db = _FakeDB([None])
    with pytest.raises(HTTPException) as exc:
        await atualizar_socio(
            socio_id="nao-existe",
            req=SocioPatch(observacoes="x"),
            db=db, cu=_user(UserRole.admin),
        )
    assert exc.value.status_code == 404


# ── Allowlist de campos (defesa em profundidade) ───────────────────────────────

async def test_patch_so_altera_campos_da_allowlist():
    """Todo campo aceito pelo PATCH tem que estar coberto pela allowlist —
    aqui SocioPatch já restringe os campos possíveis, então o teste garante
    que a allowlist não ficou desatualizada em relação ao schema."""
    from app.routers.gestao_societaria import _SOCIO_PATCH_CAMPOS

    campos_schema = set(SocioPatch.model_fields)
    assert campos_schema == _SOCIO_PATCH_CAMPOS


# ── Cadastro de sócio e aprovação de distribuição: commit único (SOC-02/DST-01) ──

async def test_cadastro_socio_commit_unico_com_auditoria():
    """POST /sociedade/socios: a auditoria é gravada na MESMA transação do
    cadastro (padrão criado no SOC-01) — antes, registrar_acao commitava o log
    em transação separada e o cadastro podia persistir sem rastro.
    Critério de aceite da issue #1073: db.commits == 1."""
    req = SocioIn(
        user_id="novosocio", participacao_percentual=0.1,
        data_entrada=date(2026, 1, 1),
    )
    # execute: consulta do "existe?" retorna None; add registra o sócio
    db = _FakeDB([None])
    out = await cadastrar_socio(req=req, db=db, cu=_user(UserRole.admin, "admin1"))
    assert out["user_id"] == "novosocio"
    assert out["participacao_percentual"] == 0.1
    assert len(db.added) == 2  # Socio + AuditLog na mesma sessão
    socio, log = db.added
    assert isinstance(socio, Socio)
    assert isinstance(log, AuditLog)
    assert log.acao == "CREATE"
    assert log.entidade == "socios"
    assert log.registro_id == socio.id
    assert log.user_id == "admin1"
    assert log.dados_depois["user_id"] == "novosocio"
    # Critério de aceite: um único commit cobre cadastro + auditoria
    assert db.commits == 1


async def test_cadastro_socio_duplicado_nao_audita():
    """Usuário já sócio → 409 e NADA é adicionado à sessão (nem audit log),
    com zero commits."""
    db = _FakeDB([_socio(user_id="duplicado", id="s2")])
    with pytest.raises(HTTPException) as exc:
        await cadastrar_socio(
            req=SocioIn(user_id="duplicado", participacao_percentual=0.05,
                        data_entrada=date(2026, 1, 1)),
            db=db, cu=_user(UserRole.admin, "admin1"),
        )
    assert exc.value.status_code == 409
    assert db.commits == 0
    assert db.added == []


async def test_aprovar_distribuicao_commit_unico_com_auditoria():
    """POST /sociedade/distribuicao/{id}/aprovar: auditoria na MESMA transação
    da aprovação (padrão criado no SOC-01) — antes, registrar_acao commitava
    o log em transação separada.
    Critério de aceite da issue #1073: db.commits == 1."""
    d = DistribuicaoLucro(
        id="dist1", mes_referencia="2026-01", valor_total=Decimal("10000.00"),
        socios_json="[]", created_by="admin1", status="calculado",
    )
    db = _FakeDB([d])
    out = await aprovar_distribuicao(dist_id="dist1", db=db,
                                     cu=_user(UserRole.admin, "admin1"))
    assert out["status"] == "aprovado"
    assert d.status == "aprovado"
    assert d.aprovado_por == "admin1"
    logs = [o for o in db.added if isinstance(o, AuditLog)]
    assert len(logs) == 1
    log = logs[0]
    assert log.acao == "UPDATE"
    assert log.entidade == "distribuicao_lucro"
    assert log.registro_id == "dist1"
    assert log.dados_antes == {"status": "calculado"}
    assert log.dados_depois == {"status": "aprovado"}
    # Critério de aceite: um único commit cobre aprovação + auditoria
    assert db.commits == 1


async def test_aprovar_distribuicao_fora_de_calculado_nao_audita():
    """Distribuição já aprovada → 422 e nenhum commit/audit."""
    d = DistribuicaoLucro(id="dist1", mes_referencia="2026-01",
                          valor_total=Decimal("10000.00"), status="aprovado",
                          socios_json="[]", created_by="admin1")
    db = _FakeDB([d])
    with pytest.raises(HTTPException) as exc:
        await aprovar_distribuicao(dist_id="dist1", db=db,
                                   cu=_user(UserRole.admin, "admin1"))
    assert exc.value.status_code == 422
    assert db.commits == 0
    assert db.added == []
