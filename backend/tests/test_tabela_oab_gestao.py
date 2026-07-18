"""Gestão da tabela OAB/MG estruturada (P0.4) — /honorarios-oab/itens.

Sem Postgres real (padrão test_provas.py). Regras absolutas cobertas:
fonte OBRIGATÓRIA (nunca inventar valor/item/vigência), versionamento por
vigência (nova vigência = novos registros; encerrar nunca altera valores),
restrição a sócio+ e auditoria.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.audit_log import AuditLog
from app.models.redesign import TabelaOABHonorario
from app.models.user import User, UserRole


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalars(self):
        return self

    def all(self):
        return self._val if isinstance(self._val, list) else []


class _FakeDB:
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


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


def _item(**kw) -> TabelaOABHonorario:
    base = dict(id="t1", item_codigo="4.1", descricao="Consulta",
                area_juridica=None, valor_minimo=300.0, percentual=None,
                unidade="R$", vigencia_inicio=None, vigencia_fim=None,
                fonte="Tabela OAB/MG (PDF institucional)", observacoes=None,
                ativo=True)
    base.update(kw)
    return TabelaOABHonorario(**base)


# ── Rotas montadas ────────────────────────────────────────────────────────────

def test_rotas_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/honorarios-oab/itens") for p in paths)
    assert any(p.endswith("/honorarios-oab/itens/{item_id}/encerrar-vigencia")
               for p in paths)


# ── Gate sócio+ ──────────────────────────────────────────────────────────────

def test_req_socio_barra_advogado_e_libera_socio():
    from app.routers.honorarios_oab import _req_socio
    with pytest.raises(HTTPException) as exc:
        _req_socio(_user(UserRole.advogado))
    assert exc.value.status_code == 403
    assert _req_socio(_user(UserRole.socio)).role == UserRole.socio
    assert _req_socio(_user(UserRole.admin)).role == UserRole.admin


# ── fonte obrigatória ────────────────────────────────────────────────────────

def test_item_sem_fonte_rejeitado_no_schema():
    from app.routers.honorarios_oab import ItemOABIn
    with pytest.raises(ValidationError):
        ItemOABIn(item_codigo="8.3", descricao="Acao de despejo")  # sem fonte
    with pytest.raises(ValidationError):
        ItemOABIn(item_codigo="8.3", descricao="Acao de despejo", fonte="x")  # curta demais


# ── Criação manual (layout 2 colunas fora do seed) ───────────────────────────

async def test_criar_item_manual_com_vigencia_informada_e_auditoria():
    from app.routers.honorarios_oab import ItemOABIn, criar_item

    db = _FakeDB([None])  # checagem de duplicidade → nada em vigência aberta
    out = await criar_item(
        body=ItemOABIn(item_codigo="8.3", descricao="Acao de despejo",
                       area_juridica="civel", valor_minimo=5000.0, percentual=20.0,
                       vigencia_inicio=date(2025, 1, 1),
                       fonte="Tabela de Honorarios OAB/MG ed. 2025 (PDF oficial)"),
        db=db, cu=_user(UserRole.socio),
    )
    itens = [o for o in db.added if isinstance(o, TabelaOABHonorario)]
    assert len(itens) == 1
    i = itens[0]
    assert i.fonte.startswith("Tabela de Honorarios OAB/MG")
    assert i.vigencia_inicio == date(2025, 1, 1)   # informada pelo usuário
    assert i.vigencia_fim is None and i.ativo is True
    assert out["item_codigo"] == "8.3" and out["valor_minimo"] == 5000.0
    assert any(isinstance(o, AuditLog) and o.acao == "CREATE"
               and o.entidade == "tabela_oab_honorarios" for o in db.added)
    assert db.commits == 1


async def test_criar_item_duplicado_em_vigencia_aberta_409():
    from app.routers.honorarios_oab import ItemOABIn, criar_item

    existente = _item(item_codigo="8.3", fonte="Tabela OAB/MG ed. 2025")
    db = _FakeDB([existente])
    with pytest.raises(HTTPException) as exc:
        await criar_item(
            body=ItemOABIn(item_codigo="8.3", descricao="Acao de despejo",
                           fonte="Tabela OAB/MG ed. 2025"),
            db=db, cu=_user(UserRole.socio),
        )
    assert exc.value.status_code == 409
    assert db.added == [] and db.commits == 0  # nunca sobrescreve


# ── Versionamento por vigência ───────────────────────────────────────────────

async def test_encerrar_vigencia_fecha_sem_alterar_valores():
    from app.routers.honorarios_oab import EncerrarVigenciaIn, encerrar_vigencia

    item = _item(vigencia_inicio=date(2024, 1, 1))
    db = _FakeDB([item])
    out = await encerrar_vigencia(
        item_id="t1", body=EncerrarVigenciaIn(vigencia_fim=date(2025, 12, 31)),
        db=db, cu=_user(UserRole.socio),
    )
    assert item.vigencia_fim == date(2025, 12, 31)
    assert item.ativo is False
    assert float(item.valor_minimo) == 300.0        # valor histórico intocado
    assert out["ativo"] is False
    audits = [o for o in db.added if isinstance(o, AuditLog)]
    assert any(a.acao == "UPDATE" and a.entidade == "tabela_oab_honorarios"
               and a.dados_antes and a.dados_antes["vigencia_fim"] is None
               for a in audits)
    assert db.commits == 1


async def test_encerrar_vigencia_ja_encerrada_409():
    from app.routers.honorarios_oab import EncerrarVigenciaIn, encerrar_vigencia

    item = _item(vigencia_fim=date(2025, 12, 31), ativo=False)
    db = _FakeDB([item])
    with pytest.raises(HTTPException) as exc:
        await encerrar_vigencia(item_id="t1",
                                body=EncerrarVigenciaIn(vigencia_fim=date(2026, 1, 1)),
                                db=db, cu=_user(UserRole.socio))
    assert exc.value.status_code == 409


async def test_encerrar_vigencia_anterior_ao_inicio_422():
    from app.routers.honorarios_oab import EncerrarVigenciaIn, encerrar_vigencia

    item = _item(vigencia_inicio=date(2025, 1, 1))
    db = _FakeDB([item])
    with pytest.raises(HTTPException) as exc:
        await encerrar_vigencia(item_id="t1",
                                body=EncerrarVigenciaIn(vigencia_fim=date(2024, 1, 1)),
                                db=db, cu=_user(UserRole.socio))
    assert exc.value.status_code == 422


async def test_nova_vigencia_gera_registro_novo_sem_tocar_no_antigo():
    from app.routers.honorarios_oab import (EncerrarVigenciaIn, ItemOABIn,
                                            criar_item, encerrar_vigencia)

    antigo = _item(item_codigo="4.1", valor_minimo=300.0,
                   fonte="Tabela OAB/MG ed. 2024")
    # 1) encerra a vigência do registro antigo (informada pelo usuário)
    db1 = _FakeDB([antigo])
    await encerrar_vigencia(item_id="t1",
                            body=EncerrarVigenciaIn(vigencia_fim=date(2025, 12, 31)),
                            db=db1, cu=_user(UserRole.socio))
    # 2) registra a NOVA vigência como NOVO registro (nunca sobrescrever)
    db2 = _FakeDB([None])
    out = await criar_item(
        body=ItemOABIn(item_codigo="4.1", descricao="Consulta",
                       valor_minimo=350.0, vigencia_inicio=date(2026, 1, 1),
                       fonte="Tabela OAB/MG ed. 2026 (documento oficial)"),
        db=db2, cu=_user(UserRole.socio),
    )
    novos = [o for o in db2.added if isinstance(o, TabelaOABHonorario)]
    assert len(novos) == 1 and novos[0].id != antigo.id
    assert float(novos[0].valor_minimo) == 350.0
    # registro antigo preservado como histórico, com valor original
    assert float(antigo.valor_minimo) == 300.0
    assert antigo.vigencia_fim == date(2025, 12, 31) and antigo.ativo is False
    assert out["vigencia_inicio"] == "2026-01-01"
