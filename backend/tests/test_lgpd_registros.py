"""LGPD como vertical de produto — ROPA (art. 37) por cliente + RIPD (art. 38).

Sem Postgres real (padrão test_sociedades_cliente.py): handlers chamados
diretamente com fake de sessão + lógica pura de services/lgpd_service. Cobre:
criação com risco DETERMINÍSTICO (sensível→alto, legítimo interesse→médio,
simples→baixo), visibilidade (advogado sem acesso ao cliente → 404), resumo/
estatísticas, soft delete (não aparece na listagem) e schema de resposta.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.client import Client
from app.models.lgpd_tratamento import BaseLegal, RegistroTratamento
from app.models.user import User, UserRole
from app.schemas.lgpd_tratamento import RegistroCreate
from app.services.lgpd_service import avaliar_risco, montar_resumo


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────

class _Scalars:
    def __init__(self, val):
        self._val = val

    def all(self):
        return list(self._val) if self._val is not None else []


class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalar(self):
        return self._val

    def scalars(self):
        return _Scalars(self._val)


class _FakeDB:
    """Sessão fake: fila de resultados para execute(); registra add + statements."""

    def __init__(self, resultados: list):
        self._resultados = list(resultados)
        self.added: list = []
        self.commits = 0
        self.statements: list = []

    async def execute(self, stmt, *a, **k):
        self.statements.append(stmt)
        return _Res(self._resultados.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


def _cliente(responsavel_id="dono") -> Client:
    return Client(id="cli1", nome="Cliente PJ", responsavel_id=responsavel_id)


def _payload(**kw) -> RegistroCreate:
    base = dict(client_id="cli1", nome_operacao="Folha de pagamento",
                finalidade="Gestão de vínculo trabalhista",
                base_legal=BaseLegal.contrato,
                categorias_dados="nome, CPF, conta bancária",
                categorias_titulares="funcionários",
                prazo_retencao="5 anos após o desligamento",
                medidas_seguranca="controle de acesso, criptografia em repouso")
    base.update(kw)
    return RegistroCreate(**base)


def _registro(**kw) -> RegistroTratamento:
    base = dict(id="reg1", client_id="cli1", nome_operacao="Folha de pagamento",
                finalidade="Gestão de vínculo trabalhista",
                base_legal=BaseLegal.contrato.value,
                categorias_dados="nome, CPF", categorias_titulares="funcionários",
                dados_sensiveis=False, transferencia_internacional=False,
                prazo_retencao="5 anos", medidas_seguranca="criptografia",
                risco="baixo", deleted_at=None)
    base.update(kw)
    return RegistroTratamento(**base)


# ── Rotas montadas ────────────────────────────────────────────────────────────

def test_rotas_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/lgpd/registros") for p in paths)
    assert any(p.endswith("/lgpd/registros/{registro_id}") for p in paths)
    assert any(p.endswith("/lgpd/registros/{client_id}/resumo") for p in paths)
    assert any(p.endswith("/lgpd/registros/{client_id}/ripd") for p in paths)
    assert any(p.endswith("/lgpd/registros/ripd/{arquivo_id}/download") for p in paths)


# ── Risco DETERMINÍSTICO (heurística honesta, sem IA) ─────────────────────────

def test_risco_simples_baixo():
    nivel, fatores = avaliar_risco(_payload())
    assert nivel == "baixo"
    assert fatores == []


def test_risco_legitimo_interesse_medio():
    nivel, fatores = avaliar_risco(_payload(base_legal=BaseLegal.legitimo_interesse))
    assert nivel == "medio"
    assert any("LIA" in f or "legítimo interesse" in f for f in fatores)


def test_risco_dados_sensiveis_alto():
    nivel, fatores = avaliar_risco(_payload(dados_sensiveis=True))
    assert nivel == "alto"
    assert any("SENSÍVEIS" in f or "art. 11" in f for f in fatores)


def test_risco_transferencia_internacional_sobe():
    nivel, fatores = avaliar_risco(_payload(transferencia_internacional=True))
    assert nivel == "medio"
    assert any("internacional" in f for f in fatores)


def test_risco_soma_de_fatores_vira_alto():
    # legítimo interesse (+1) + transferência internacional (+1) = alto.
    nivel, _ = avaliar_risco(_payload(base_legal=BaseLegal.legitimo_interesse,
                                      transferencia_internacional=True))
    assert nivel == "alto"


# ── Criação (risco calculado no service + audit log) ──────────────────────────

async def test_criacao_calcula_risco_e_audita():
    from app.models.audit_log import AuditLog
    from app.routers.lgpd_registros import criar

    db = _FakeDB([_cliente()])  # gestão: só a query do cliente
    out = await criar(payload=_payload(dados_sensiveis=True),
                      db=db, cu=_user(UserRole.socio))
    assert out["risco"] == "alto"
    assert out["fatores_risco"]  # não vazio
    assert out["dados_sensiveis"] is True
    regs = [o for o in db.added if isinstance(o, RegistroTratamento)]
    assert len(regs) == 1 and regs[0].risco == "alto"
    assert any(isinstance(o, AuditLog) and o.entidade == "lgpd_registros_tratamento"
               for o in db.added)
    assert db.commits == 1


async def test_criacao_para_cliente_fora_do_escopo_404():
    from app.routers.lgpd_registros import criar

    # advogado u1 não é responsável pelo cliente e não atua em caso dele (None).
    db = _FakeDB([_cliente(responsavel_id="outro"), None])
    with pytest.raises(HTTPException) as exc:
        await criar(payload=_payload(), db=db, cu=_user(UserRole.advogado))
    assert exc.value.status_code == 404
    assert db.added == []


# ── Visibilidade (matriz de casos, espelhada de sociedades) ───────────────────

async def test_advogado_sem_acesso_ao_cliente_404():
    from app.routers.lgpd_registros import _carregar_registro

    # registro existe, cliente de outro responsável, nenhum caso do advogado.
    db = _FakeDB([_registro(), _cliente(responsavel_id="outro"), None])
    with pytest.raises(HTTPException) as exc:
        await _carregar_registro(db, _user(UserRole.advogado), "reg1")
    assert exc.value.status_code == 404


async def test_gestao_ve_tudo():
    from app.routers.lgpd_registros import _carregar_registro

    db = _FakeDB([_registro(), _cliente(responsavel_id="outro")])
    reg = await _carregar_registro(db, _user(UserRole.socio), "reg1")
    assert reg.id == "reg1"


async def test_registro_inexistente_404():
    from app.routers.lgpd_registros import _carregar_registro

    db = _FakeDB([None])
    with pytest.raises(HTTPException) as exc:
        await _carregar_registro(db, _user(UserRole.socio), "nao-existe")
    assert exc.value.status_code == 404


# ── Resumo / estatísticas do ROPA ─────────────────────────────────────────────

def test_resumo_estatisticas_corretas():
    registros = [
        SimpleNamespace(dados_sensiveis=True, transferencia_internacional=False, risco="alto"),
        SimpleNamespace(dados_sensiveis=False, transferencia_internacional=True, risco="medio"),
        SimpleNamespace(dados_sensiveis=False, transferencia_internacional=False, risco="baixo"),
    ]
    r = montar_resumo(registros)
    assert r["total_operacoes"] == 3
    assert r["com_dados_sensiveis"] == 1
    assert r["com_transferencia_internacional"] == 1
    assert r["distribuicao_risco"] == {"alto": 1, "medio": 1, "baixo": 1}


def test_resumo_vazio():
    r = montar_resumo([])
    assert r["total_operacoes"] == 0
    assert r["distribuicao_risco"] == {"alto": 0, "medio": 0, "baixo": 0}


async def test_resumo_handler_valida_acesso_404():
    from app.routers.lgpd_registros import resumo

    db = _FakeDB([_cliente(responsavel_id="outro"), None])  # advogado sem acesso
    with pytest.raises(HTTPException) as exc:
        await resumo(client_id="cli1", db=db, cu=_user(UserRole.advogado))
    assert exc.value.status_code == 404


# ── Soft delete ───────────────────────────────────────────────────────────────

async def test_remover_soft_delete_e_audita():
    from app.models.audit_log import AuditLog
    from app.routers.lgpd_registros import remover

    reg = _registro()
    db = _FakeDB([reg, _cliente()])  # gestão
    out = await remover(registro_id="reg1", db=db, cu=_user(UserRole.socio))
    assert "removido" in out.detail.lower()
    assert reg.deleted_at is not None  # soft delete (nunca DELETE físico)
    assert any(isinstance(o, AuditLog) and o.acao == "DELETE" for o in db.added)


async def test_listagem_filtra_soft_delete_e_serializa_risco():
    from app.routers.lgpd_registros import listar

    ativos = [_registro(id="a", risco="baixo"),
              _registro(id="b", dados_sensiveis=True, risco="alto")]
    db = _FakeDB([ativos])  # gestão: uma query só
    out = await listar(client_id="cli1", db=db, cu=_user(UserRole.socio))
    assert out["total"] == 2
    assert {d["id"] for d in out["data"]} == {"a", "b"}
    # Cada item traz risco + fatores.
    assert all("risco" in d and "fatores_risco" in d for d in out["data"])
    # A query de listagem filtra soft delete no SQL (não vaza deletados).
    assert "deleted_at IS NULL" in str(db.statements[0])


# ── Schema de resposta / validação de entrada ─────────────────────────────────

def test_schema_valida_enum_e_limites():
    # base_legal inválida é rejeitada pelo enum.
    with pytest.raises(Exception):
        _payload(base_legal="inexistente")
    # nome_operacao muito curto é rejeitado (min_length).
    with pytest.raises(Exception):
        _payload(nome_operacao="x")
    # payload válido normaliza o enum.
    p = _payload(base_legal=BaseLegal.consentimento)
    assert p.base_legal == BaseLegal.consentimento
