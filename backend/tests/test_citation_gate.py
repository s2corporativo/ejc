"""Gate antialucinação de citações (Fase 4 — citation_gate + HITL).

Cobre: políticas bloquear/marcar/desligado, critérios de bloqueio (suspeita,
genérica, julgado sem tribunal+data), verificação contra base mockada
(verificada vs não verificada), gate no endpoint HITL (409 sem override,
override justificado auditado) e montagem da rota POST /ia/validar-citacoes.
"""
import pytest
from fastapi import HTTPException

from app.services.citation_gate import (
    RelatorioCitacoes, avaliar_bloqueantes, validar_citacoes,
)


# ── Fakes de banco (mesmo padrão de test_citation_check) ─────────────────────

class _RowVazia:
    def first(self):
        return None


class _DBVazio:
    """Base RAG vazia: nenhuma súmula/artigo confirmado."""
    async def execute(self, *a, **k):
        return _RowVazia()


class _RowConfirma:
    def first(self):
        return ("Súmula 7 STJ — reexame de prova",)


class _DBConfirma:
    """Base RAG que confirma qualquer súmula/artigo consultado."""
    async def execute(self, *a, **k):
        return _RowConfirma()


TEXTO_SUSPEITO = "Nos termos da Súmula 9999 do STJ, o pedido procede."
TEXTO_GENERICO = "A jurisprudência pacífica dos tribunais ampara o pedido."
TEXTO_JULGADO_INCOMPLETO = "Conforme decidido no REsp 1.737.428, aplica-se a tese."
TEXTO_JULGADO_COMPLETO = (
    "Conforme o REsp 1.737.428/SP, Terceira Turma do STJ, Rel. Min. Nancy "
    "Andrighi, julgado em 12/02/2019, aplica-se a tese."
)
TEXTO_SUMULA_OK = "Aplica-se a Súmula 7 do STJ ao caso concreto."


# ── validar_citacoes: políticas ──────────────────────────────────────────────

async def test_politica_desligado_nao_verifica_nada():
    r = await validar_citacoes(_DBVazio(), TEXTO_SUSPEITO, politica="desligado")
    assert isinstance(r, RelatorioCitacoes)
    assert r.politica == "desligado"
    assert r.relatorio is None
    assert r.bloqueia_aprovacao is False
    assert r.total == 0


async def test_politica_marcar_lista_bloqueantes_mas_nao_bloqueia():
    r = await validar_citacoes(_DBVazio(), TEXTO_SUSPEITO, politica="marcar")
    assert r.bloqueia_aprovacao is False           # marcar nunca bloqueia
    assert r.bloqueantes                            # ... mas expõe ao revisor
    assert r.bloqueantes[0].status == "suspeita"
    assert r.motivos


async def test_politica_bloquear_com_suspeita_bloqueia():
    r = await validar_citacoes(_DBVazio(), TEXTO_SUSPEITO, politica="bloquear")
    assert r.bloqueia_aprovacao is True
    assert r.nao_verificadas >= 1


async def test_politica_bloquear_mencao_generica_bloqueia():
    r = await validar_citacoes(_DBVazio(), TEXTO_GENERICO, politica="bloquear")
    assert r.bloqueia_aprovacao is True
    assert any(b.status == "generica" for b in r.bloqueantes)


async def test_julgado_sem_data_bloqueia_em_bloquear():
    # REsp identificado (tribunal STJ implícito pela classe), mas SEM data.
    r = await validar_citacoes(
        _DBVazio(), TEXTO_JULGADO_INCOMPLETO, politica="bloquear")
    assert r.bloqueia_aprovacao is True
    assert any("data" in b.motivo for b in r.bloqueantes)


async def test_julgado_completo_nao_bloqueia():
    # Julgado com tribunal + data no contexto: identificada plausível → passa
    # (confirmação de inteiro teor é do revisor; base local não tem acórdãos).
    r = await validar_citacoes(
        _DBVazio(), TEXTO_JULGADO_COMPLETO, politica="bloquear")
    assert r.bloqueia_aprovacao is False
    assert r.bloqueantes == []


async def test_sumula_confirmada_na_base_verificada_e_nao_bloqueia():
    r = await validar_citacoes(_DBConfirma(), TEXTO_SUMULA_OK, politica="bloquear")
    assert r.verificadas >= 1
    assert r.bloqueia_aprovacao is False
    # relatório integral preservado (shape do verificador rigoroso)
    assert r.relatorio and r.relatorio["confirmadas"] == r.verificadas


async def test_sumula_nao_confirmada_conta_como_nao_verificada():
    r = await validar_citacoes(_DBVazio(), TEXTO_SUMULA_OK, politica="marcar")
    assert r.verificadas == 0
    assert r.nao_verificadas == r.total >= 1
    # Súmula em faixa plausível não é bloqueante (é "identificada", não julgado)
    assert r.bloqueia_aprovacao is False


async def test_texto_sem_citacoes_nunca_bloqueia():
    r = await validar_citacoes(_DBVazio(), "Texto sem citação.", politica="bloquear")
    assert r.total == 0 and r.bloqueia_aprovacao is False


def test_politica_invalida_cai_no_default_marcar(monkeypatch):
    from app.core.config import get_settings
    from app.services.citation_gate import politica_citacoes
    monkeypatch.setattr(get_settings(), "CITACOES_POLITICA", "banana")
    assert politica_citacoes() == "marcar"


def test_avaliar_bloqueantes_ignora_verificadas_e_identificadas_completas():
    rel = {"citacoes": [
        {"status": "verificada", "tipo": "sumula", "citacao": "Súmula 7 STJ"},
        {"status": "identificada", "tipo": "recurso", "citacao": "REsp 1",
         "tribunal": "STJ", "data": "12/02/2019"},
        {"status": "identificada", "tipo": "artigo", "citacao": "art. 5 CF"},
    ]}
    assert avaliar_bloqueantes(rel) == []


# ── Gate no fluxo HITL (PATCH /ai/logs/{id}/hitl) ────────────────────────────

class _Role:
    value = "advogado"


class _CU:
    id = "user-1"
    role = _Role()


class _FakeLog:
    def __init__(self, resposta):
        self.id = "log-1"
        self.user_id = "user-1"
        self.resposta = resposta
        self.fontes_rag = None
        self.status_hitl = None
        self.revisado_por = None
        self.revisado_em = None


class _ResultHITL:
    """Serve tanto o select(AILog) quanto os lookups text() do verificador."""
    def __init__(self, log):
        self._log = log

    def scalar_one_or_none(self):
        return self._log

    def first(self):
        return None  # base RAG vazia


class _DBHITL:
    def __init__(self, log):
        self.log = log

    async def execute(self, *a, **k):
        return _ResultHITL(self.log)

    async def commit(self):
        pass


def _forca_politica(monkeypatch, valor):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "CITACOES_POLITICA", valor)


async def test_hitl_bloqueia_aprovacao_sem_override(monkeypatch):
    _forca_politica(monkeypatch, "bloquear")
    from app.routers.ai import atualizar_hitl
    from app.schemas.ai import HITLRevisaoRequest
    log = _FakeLog(TEXTO_SUSPEITO)
    with pytest.raises(HTTPException) as exc:
        await atualizar_hitl("log-1", HITLRevisaoRequest(status="aplicado"),
                             db=_DBHITL(log), cu=_CU())
    assert exc.value.status_code == 409
    assert exc.value.detail["erro"] == "citacoes_nao_verificadas"
    assert exc.value.detail["bloqueantes"]


async def test_hitl_override_exige_justificativa(monkeypatch):
    _forca_politica(monkeypatch, "bloquear")
    from app.routers.ai import atualizar_hitl
    from app.schemas.ai import HITLRevisaoRequest
    log = _FakeLog(TEXTO_SUSPEITO)
    req = HITLRevisaoRequest(status="aplicado", override_citacoes=True,
                             justificativa_override="curta")
    with pytest.raises(HTTPException) as exc:
        await atualizar_hitl("log-1", req, db=_DBHITL(log), cu=_CU())
    assert exc.value.status_code == 422


async def test_hitl_override_justificado_aprova_e_audita(monkeypatch):
    _forca_politica(monkeypatch, "bloquear")
    from app.routers.ai import atualizar_hitl
    from app.schemas.ai import HITLRevisaoRequest
    log = _FakeLog(TEXTO_SUSPEITO)
    req = HITLRevisaoRequest(
        status="aplicado", override_citacoes=True,
        justificativa_override="Confirmei o inteiro teor no site do STJ.")
    r = await atualizar_hitl("log-1", req, db=_DBHITL(log), cu=_CU())
    assert "aplicado" in r["detail"]
    assert "[override_citacoes]" in log.fontes_rag
    assert "por=user-1" in log.fontes_rag


async def test_hitl_politica_marcar_nao_bloqueia(monkeypatch):
    _forca_politica(monkeypatch, "marcar")
    from app.routers.ai import atualizar_hitl
    from app.schemas.ai import HITLRevisaoRequest
    log = _FakeLog(TEXTO_SUSPEITO)
    r = await atualizar_hitl("log-1", HITLRevisaoRequest(status="revisado"),
                             db=_DBHITL(log), cu=_CU())
    assert "revisado" in r["detail"]
    assert log.fontes_rag is None  # sem override → sem rastro extra


async def test_hitl_descartar_nunca_bloqueia(monkeypatch):
    _forca_politica(monkeypatch, "bloquear")
    from app.routers.ai import atualizar_hitl
    from app.schemas.ai import HITLRevisaoRequest
    log = _FakeLog(TEXTO_SUSPEITO)
    r = await atualizar_hitl("log-1", HITLRevisaoRequest(status="descartado"),
                             db=_DBHITL(log), cu=_CU())
    assert "descartado" in r["detail"]


# ── Endpoint sob demanda + validador de resposta ─────────────────────────────

def test_rota_validar_citacoes_montada():
    from app.main import app
    paths = {r.path for r in app.routes}
    assert "/api/ia/validar-citacoes" in paths
    assert "/api/ai/logs/{log_id}/citacoes" in paths


async def test_response_validator_respeita_politica_desligado(monkeypatch):
    _forca_politica(monkeypatch, "desligado")
    from app.services.ai.core import response_validator

    class _DBExplode:
        async def execute(self, *a, **k):
            raise AssertionError("não deveria consultar a base com política desligada")

    r = await response_validator.validar(
        _DBExplode(), TEXTO_SUSPEITO, exige_fonte=True, fontes=[{"x": 1}])
    assert r["citacoes"] is None


async def test_response_validator_alerta_bloqueio_em_politica_bloquear(monkeypatch):
    _forca_politica(monkeypatch, "bloquear")
    from app.services.ai.core import response_validator
    r = await response_validator.validar(
        _DBVazio(), TEXTO_SUSPEITO, exige_fonte=True, fontes=[{"x": 1}])
    assert any("BLOQUEANTE" in a for a in r["alertas"])
    assert r["revisao_obrigatoria"] is True
