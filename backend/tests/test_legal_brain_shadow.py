from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.legal_brain import shadow


@pytest.mark.asyncio
async def test_shadow_chama_orquestrador_uma_vez_e_preserva_resposta(monkeypatch):
    core_result = {
        "conteudo": "Resposta original",
        "provider": "fake",
        "revisao_obrigatoria": True,
        "log_id": "log-1",
    }
    run = AsyncMock(return_value=core_result)
    monkeypatch.setattr(shadow, "orchestrator", SimpleNamespace(run=run))

    result = await shadow.run_shadow_ai_task(
        task_type="analise_juridica",
        domain="bancario",
        mensagem="Revisar financiamento, juros e prova.",
        params={"module_key": "inteligencia"},
    )

    run.assert_awaited_once()
    assert result["conteudo"] == core_result["conteudo"]
    assert result["provider"] == core_result["provider"]
    assert result["revisao_obrigatoria"] is True
    assert result["log_id"] == "log-1"
    assert result["legal_brain_shadow"]["metadata"]["deterministic"] is True
    assert result["legal_brain_shadow"]["issues"]
    assert "legal_brain_shadow" not in core_result


@pytest.mark.asyncio
async def test_shadow_nao_envia_plano_para_orquestrador(monkeypatch):
    run = AsyncMock(return_value={"conteudo": "ok"})
    monkeypatch.setattr(shadow, "orchestrator", SimpleNamespace(run=run))

    kwargs = {
        "task_type": "chat",
        "domain": "civil",
        "mensagem": "Dúvida sobre competência e prova.",
        "params": {"surface": "/inteligencia"},
    }
    await shadow.run_shadow_ai_task(**kwargs)

    passed = run.await_args.kwargs
    assert passed == kwargs
    assert "legal_brain_shadow" not in passed.get("params", {})
