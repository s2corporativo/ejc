"""Regressão do diagnóstico de coletor de erros persistente."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.diagnostico_service import _probe_erros, agregar


@pytest.mark.asyncio
async def test_sem_coletor_persistente_e_alerta():
    item = await _probe_erros(SimpleNamespace(SENTRY_DSN=None))

    assert item["status"] == "alerta"
    assert item["coletor"] is None
    assert "logs efêmeros" in item["detalhe"]

    geral, resumo = agregar([item])
    assert geral == "alerta"
    assert resumo["alerta"] == 1
    assert resumo["ok"] == 0


@pytest.mark.asyncio
async def test_sentry_configurado_e_ok_sem_expor_dsn():
    segredo = "https://chave-secreta@erros.example/123"
    item = await _probe_erros(SimpleNamespace(SENTRY_DSN=segredo))

    assert item["status"] == "ok"
    assert item["coletor"] == "sentry"
    assert segredo not in str(item)
