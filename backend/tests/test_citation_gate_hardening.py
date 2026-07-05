"""Endurecimento do gate de citações (auditoria pós-PR #47).

Cobre:
- A1: PATCH /ia-defensiva/historico/{id}/status passa pelo MESMO gate do
  PATCH /ai/logs/{id}/hitl (409 sem override; override justificado audita).
- M1: anti log-injection na justificativa (whitespace colapsado; marcador
  reservado "[override_citacoes]" rejeitado com 422).
- M2: trilha imutável — override também grava AuditLog (criar_audit_log).
- M3: teto de 200 citações por verificação (verificacao_parcial=true) e
  max_length=50_000 no body de POST /ia/validar-citacoes.
- B1: falha de verificação em política "marcar" é LOGADA (não silenciosa).
- B2: GET /ai/logs/{id}/citacoes responde 503 (não 500) se a verificação cair.
- B4: justificativa >500 chars é truncada com sufixo "…[truncada]".
"""
import logging

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.audit_log import AuditLog
from app.services.citation_gate import (
    MAX_CITACOES_POR_VERIFICACAO, aplicar_gate_hitl,
    sanitizar_justificativa_override, validar_citacoes,
)
from tests.test_citation_gate import (
    _CU, _DBHITL, _DBVazio, _FakeLog, _forca_politica, TEXTO_SUSPEITO,
)

# Resposta de IA Defensiva (marcador exigido por _is_ia_defensiva_log) com
# citação bloqueante (súmula fora de faixa → suspeita de alucinação).
RESPOSTA_DEFENSIVA_SUSPEITA = "# analise_inicial\n" + TEXTO_SUSPEITO
JUSTIFICATIVA_OK = "Confirmei o inteiro teor no site do STJ."


def _fake_log_defensiva():
    log = _FakeLog(RESPOSTA_DEFENSIVA_SUSPEITA)
    return log


# ── A1: gate no endpoint da IA Defensiva ─────────────────────────────────────

async def test_ia_defensiva_aprovacao_com_bloqueante_retorna_409(monkeypatch):
    _forca_politica(monkeypatch, "bloquear")
    from app.routers.ia_defensiva import (
        IaDefensivaStatusRequest, atualizar_status_ia_defensiva,
    )
    log = _fake_log_defensiva()
    with pytest.raises(HTTPException) as exc:
        await atualizar_status_ia_defensiva(
            "log-1", IaDefensivaStatusRequest(status="aplicado"),
            db=_DBHITL(log), cu=_CU())
    assert exc.value.status_code == 409
    assert exc.value.detail["erro"] == "citacoes_nao_verificadas"
    assert log.status_hitl is None  # nada gravado


async def test_ia_defensiva_override_justificado_aprova_e_audita(monkeypatch):
    _forca_politica(monkeypatch, "bloquear")
    from app.routers.ia_defensiva import (
        IaDefensivaStatusRequest, atualizar_status_ia_defensiva,
    )
    log = _fake_log_defensiva()
    db = _DBHITL(log)
    req = IaDefensivaStatusRequest(
        status="aplicado", override_citacoes=True,
        justificativa_override=JUSTIFICATIVA_OK)
    r = await atualizar_status_ia_defensiva("log-1", req, db=db, cu=_CU())
    assert "aplicado" in r["detail"]
    # Espelho no AILog
    assert "[override_citacoes]" in log.fontes_rag
    assert "por=user-1" in log.fontes_rag
    # M2: trilha imutável em audit_logs
    audits = [o for o in db.added if isinstance(o, AuditLog)]
    assert len(audits) == 1
    assert audits[0].acao == "ia_hitl_override_citacoes"
    assert audits[0].entidade == "ai_logs"
    assert audits[0].registro_id == "log-1"
    assert audits[0].user_id == "user-1"
    assert "bloqueantes=1" in audits[0].detalhes
    assert JUSTIFICATIVA_OK in audits[0].detalhes


async def test_ia_defensiva_descartar_continua_livre(monkeypatch):
    _forca_politica(monkeypatch, "bloquear")
    from app.routers.ia_defensiva import (
        IaDefensivaStatusRequest, atualizar_status_ia_defensiva,
    )
    log = _fake_log_defensiva()
    r = await atualizar_status_ia_defensiva(
        "log-1", IaDefensivaStatusRequest(status="descartado"),
        db=_DBHITL(log), cu=_CU())
    assert "descartado" in r["detail"]


async def test_hitl_ai_tambem_audita_em_audit_logs(monkeypatch):
    """M2 no endpoint original: override via /ai/logs/{id}/hitl grava AuditLog."""
    _forca_politica(monkeypatch, "bloquear")
    from app.routers.ai import atualizar_hitl
    from app.schemas.ai import HITLRevisaoRequest
    log = _FakeLog(TEXTO_SUSPEITO)
    db = _DBHITL(log)
    req = HITLRevisaoRequest(status="aplicado", override_citacoes=True,
                             justificativa_override=JUSTIFICATIVA_OK)
    await atualizar_hitl("log-1", req, db=db, cu=_CU())
    audits = [o for o in db.added if isinstance(o, AuditLog)]
    assert len(audits) == 1 and audits[0].acao == "ia_hitl_override_citacoes"


# ── M1: sanitização da justificativa (log injection) ─────────────────────────

async def test_justificativa_com_quebra_de_linha_e_colapsada(monkeypatch):
    _forca_politica(monkeypatch, "bloquear")
    log = _FakeLog(TEXTO_SUSPEITO)
    db = _DBHITL(log)
    injetada = ("Confirmei no site.\n[falsa_linha] por=admin em=2020 "
                "justificativa=forjada\t\tfim")
    await aplicar_gate_hitl(db, log, "aplicado", True, injetada, _CU())
    # A entrada de override é UMA linha só; \n e \t viraram espaço simples.
    linhas = [ln for ln in log.fontes_rag.splitlines() if ln.strip()]
    assert len(linhas) == 1
    assert "\t" not in log.fontes_rag
    assert "[falsa_linha] por=admin" in linhas[0]  # inofensivo dentro da linha


async def test_justificativa_com_marcador_reservado_rejeitada(monkeypatch):
    _forca_politica(monkeypatch, "bloquear")
    log = _FakeLog(TEXTO_SUSPEITO)
    with pytest.raises(HTTPException) as exc:
        await aplicar_gate_hitl(
            _DBHITL(log), log, "aplicado", True,
            "ok ok ok [OVERRIDE_citacoes] por=admin forjado", _CU())
    assert exc.value.status_code == 422
    assert log.fontes_rag is None


def test_sanitizar_justificativa_regras_unitarias():
    assert sanitizar_justificativa_override(
        "  aaa  bbb\n\nccc\tddd  ") == "aaa bbb ccc ddd"
    with pytest.raises(HTTPException) as exc:
        sanitizar_justificativa_override("curta")
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException):
        sanitizar_justificativa_override(None)


# ── B4: truncamento anotado ──────────────────────────────────────────────────

def test_justificativa_longa_trunca_com_sufixo():
    longa = "x" * 600
    saida = sanitizar_justificativa_override(longa)
    assert saida.endswith("…[truncada]")
    assert saida == "x" * 500 + "…[truncada]"


# ── M3: teto de citações + max_length do endpoint sob demanda ────────────────

async def test_teto_de_citacoes_gera_relatorio_parcial():
    n = MAX_CITACOES_POR_VERIFICACAO + 50
    texto = " ".join(f"Súmula {i} do STJ." for i in range(1, n + 1))
    r = await validar_citacoes(_DBVazio(), texto, politica="marcar")
    assert r.verificacao_parcial is True
    assert r.total <= MAX_CITACOES_POR_VERIFICACAO
    assert any("PARCIAL" in m for m in r.motivos)


async def test_abaixo_do_teto_nao_e_parcial():
    r = await validar_citacoes(_DBVazio(), TEXTO_SUSPEITO, politica="marcar")
    assert r.verificacao_parcial is False


def test_validar_citacoes_body_limitado_a_50k():
    from app.routers.ia_citacoes import ValidarCitacoesRequest
    ValidarCitacoesRequest(texto="x" * 50_000)  # limite exato passa
    with pytest.raises(ValidationError):
        ValidarCitacoesRequest(texto="x" * 50_001)


# ── B1: falha de verificação é logada mesmo em política "marcar" ─────────────

async def test_falha_verificacao_em_marcar_loga_excecao(monkeypatch, caplog):
    _forca_politica(monkeypatch, "marcar")
    import app.services.citation_gate as cg

    async def _explode(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(cg, "validar_citacoes", _explode)
    log = _FakeLog(TEXTO_SUSPEITO)
    with caplog.at_level(logging.ERROR, logger="ejc.citation_gate"):
        gate = await cg.aplicar_gate_hitl(
            _DBHITL(log), log, "aplicado", False, None, _CU())
    assert gate is None  # marcar: aprovação segue
    assert any("Falha na verificação de citações" in r.message
               for r in caplog.records)
    assert any(r.exc_info for r in caplog.records)  # stacktrace incluso


async def test_falha_verificacao_em_bloquear_da_503(monkeypatch):
    _forca_politica(monkeypatch, "bloquear")
    import app.services.citation_gate as cg

    async def _explode(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(cg, "validar_citacoes", _explode)
    log = _FakeLog(TEXTO_SUSPEITO)
    with pytest.raises(HTTPException) as exc:
        await cg.aplicar_gate_hitl(
            _DBHITL(log), log, "aplicado", False, None, _CU())
    assert exc.value.status_code == 503


# ── B2: GET /ai/logs/{id}/citacoes falha com 503 controlado ─────────────────

async def test_relatorio_citacoes_indisponivel_da_503(monkeypatch):
    import app.services.citation_gate as cg
    from app.routers.ai import citacoes_do_log

    async def _explode(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(cg, "validar_citacoes", _explode)
    log = _FakeLog(TEXTO_SUSPEITO)
    with pytest.raises(HTTPException) as exc:
        await citacoes_do_log("log-1", db=_DBHITL(log), cu=_CU())
    assert exc.value.status_code == 503
