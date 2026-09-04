"""Regressões P0 para o piso de sigilo da expansão HyDE (#1464)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_hyde_hardening_forca_local_completo(monkeypatch):
    # app.main instala o hardening canônico do núcleo no startup/import.
    from app.main import app  # noqa: F401
    from app.services import ai_service
    from app.services.ai.sanitization_policy import ModoSanitizacao

    monkeypatch.setattr(ai_service.settings, "RAG_HYDE_ENABLED", True)
    captura = {}

    async def fake_chat(messages, **kwargs):
        captura["messages"] = messages
        captura.update(kwargs)
        return SimpleNamespace(texto="hipotese juridica generica")

    monkeypatch.setattr(ai_service, "gw_chat", fake_chat)

    resultado = await ai_service._hyde_expandir("consulta juridica ficticia")

    assert resultado.endswith("hipotese juridica generica")
    assert captura["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO
    assert captura["task_type"] == "resumo"


@pytest.mark.asyncio
async def test_hyde_local_indisponivel_nao_faz_fallback_externo(monkeypatch):
    from app.main import app  # noqa: F401
    from app.services import ai_service

    monkeypatch.setattr(ai_service.settings, "RAG_HYDE_ENABLED", True)
    chamadas = 0

    async def local_indisponivel(*args, **kwargs):
        nonlocal chamadas
        chamadas += 1
        raise RuntimeError("provider local indisponivel")

    monkeypatch.setattr(ai_service, "gw_chat", local_indisponivel)
    consulta = "consulta sigilosa ficticia"

    resultado = await ai_service._hyde_expandir(consulta)

    assert resultado == consulta
    # Uma única tentativa: o wrapper não inicia segunda chamada/fallback externo.
    assert chamadas == 1


@pytest.mark.asyncio
async def test_hyde_desligado_nao_chama_gateway(monkeypatch):
    from app.main import app  # noqa: F401
    from app.services import ai_service

    monkeypatch.setattr(ai_service.settings, "RAG_HYDE_ENABLED", False)

    async def proibido(*args, **kwargs):
        raise AssertionError("gateway não deveria ser chamado com HyDE desligado")

    monkeypatch.setattr(ai_service, "gw_chat", proibido)
    consulta = "consulta ficticia"

    assert await ai_service._hyde_expandir(consulta) == consulta
