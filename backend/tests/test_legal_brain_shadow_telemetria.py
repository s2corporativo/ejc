"""LB9: telemetria de divergência do shadow, inércia e tolerância a falhas."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.legal_brain import shadow
from app.services.legal_brain.brain import build_legal_brain_plan

_MSG = "Revisar financiamento do João da Silva CPF 123.456.789-00, juros e prova."
_LOGGER = "ejc.legal_brain.shadow"


def _plan(msg=_MSG):
    return build_legal_brain_plan(
        task_type="analise_juridica", domain="bancario", message=msg
    )


def _patch_run(monkeypatch, core):
    run = AsyncMock(return_value=core)
    monkeypatch.setattr(shadow, "orchestrator", SimpleNamespace(run=run))
    return run


def test_compare_shadow_deterministico_e_sem_pii():
    plan = _plan()
    legacy = {"conteudo": "Texto sigiloso do cliente João", "fontes": [], "alertas": []}
    r1 = shadow.compare_shadow(legacy, plan)
    assert r1 == shadow.compare_shadow(legacy, plan)
    assert r1["legacy_fontes_count"] == 0
    assert r1["diverged"] is True
    assert "legado_sem_fontes_plano_exige_evidencia" in r1["divergences"]
    blob = repr(r1)
    for proibido in ("João", "Silva", "123.456", "sigiloso", "financiamento do"):
        assert proibido not in blob


def test_compare_shadow_com_fontes_e_resposta_malformada():
    plan = _plan()
    ok = shadow.compare_shadow({"fontes": [{"fonte": "x"}], "alertas": ["a"]}, plan)
    assert ok["legacy_fontes_count"] == 1
    assert "legado_sem_fontes_plano_exige_evidencia" not in ok["divergences"]
    assert shadow.compare_shadow(None, plan)["legacy_fontes_count"] == 0


@pytest.mark.asyncio
async def test_shadow_emite_log_agregado_sem_texto(monkeypatch, caplog):
    _patch_run(monkeypatch, {"conteudo": "RESPOSTA SIGILOSA", "fontes": [], "alertas": []})
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        await shadow.run_shadow_ai_task(
            task_type="analise_juridica", domain="bancario", mensagem=_MSG, params={}
        )
    recs = [r for r in caplog.records if r.name == _LOGGER]
    assert len(recs) == 1 and recs[0].levelno == logging.INFO
    assert recs[0].shadow_report["issues_count"] >= 1
    text = caplog.text + repr(recs[0].__dict__)
    for proibido in ("SIGILOSA", "João", "123.456"):
        assert proibido not in text


@pytest.mark.asyncio
async def test_shadow_so_adiciona_a_chave_e_nao_muta_legado(monkeypatch):
    core = {"conteudo": "x", "fontes": [{"fonte": "a"}], "alertas": ["w"], "log_id": "1"}
    snapshot = {"conteudo": "x", "fontes": [{"fonte": "a"}], "alertas": ["w"], "log_id": "1"}
    run = _patch_run(monkeypatch, core)
    out = await shadow.run_shadow_ai_task(task_type="chat", domain="civil", mensagem=_MSG)
    assert core == snapshot
    assert set(out) - set(snapshot) == {"legal_brain_shadow"}
    assert {k: v for k, v in out.items() if k != "legal_brain_shadow"} == snapshot
    run.assert_awaited_once()


@pytest.mark.asyncio
async def test_shadow_engole_falha_da_telemetria(monkeypatch, caplog):
    core = {"conteudo": "x"}
    _patch_run(monkeypatch, core)

    def boom(*a, **k):
        raise RuntimeError("falha interna")

    monkeypatch.setattr(shadow, "compare_shadow", boom)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        out = await shadow.run_shadow_ai_task(task_type="chat", domain="civil", mensagem=_MSG)
    assert out == core
    assert "legal_brain_shadow_telemetry_failed" in caplog.text


@pytest.mark.asyncio
async def test_shadow_engole_falha_do_plano_sem_provedor_extra(monkeypatch, caplog):
    core = {"conteudo": "x"}
    run = _patch_run(monkeypatch, core)

    def boom(**k):
        raise RuntimeError("falha plano")

    monkeypatch.setattr(shadow, "build_legal_brain_plan", boom)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        out = await shadow.run_shadow_ai_task(task_type="chat", domain="civil", mensagem=_MSG)
    assert out == core
    run.assert_awaited_once()
    assert "legal_brain_shadow_plan_failed" in caplog.text
