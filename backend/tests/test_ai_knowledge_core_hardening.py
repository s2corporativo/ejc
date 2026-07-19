"""Regressões críticas da auditoria do núcleo de IA e conhecimento jurídico."""
from __future__ import annotations

from types import SimpleNamespace

import pytest


async def test_gateway_fail_closed_nao_contorna_kill_switch(monkeypatch):
    # Importar app instala o patch na primitiva interna usada por todos os aliases
    # de chat, inclusive os importados antes do startup.
    from app.main import app  # noqa: F401
    from app.core.config import get_settings
    from app.services import ai_gateway

    s = get_settings()
    monkeypatch.setattr(s, "AI_EXTERNAL_PROVIDERS_ALLOWED", False)
    monkeypatch.setattr(s, "OLLAMA_ENABLED", False)
    monkeypatch.setattr(s, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(s, "MARITACA_ENABLED", True)
    monkeypatch.setattr(s, "MARITACA_API_KEY", "fake")
    monkeypatch.setattr(s, "GROQ_API_KEY", "fake")

    chamados: list[str] = []

    async def _provider_nao_pode_ser_chamado(provider, *args, **kwargs):
        chamados.append(provider)
        raise AssertionError("kill-switch externo foi ignorado")

    monkeypatch.setattr(ai_gateway, "_chamar_provedor", _provider_nao_pode_ser_chamado)

    with pytest.raises(RuntimeError):
        await ai_gateway.chat(
            [{"role": "user", "content": "consulta jurídica sem dados pessoais"}],
            task_type="analise_juridica",
        )
    assert chamados == []


def test_ailog_pseudonimiza_resposta_e_critica_no_write_path():
    from app.models.ai_log import AILog, AITipoUso

    log = AILog(
        id="log-fake",
        user_id="user-fake",
        tipo_uso=AITipoUso.analise_caso,
        modelo="llama-3.3-70b-versatile",
        prompt_sanitizado="consulta limpa",
        resposta=(
            "A cliente Maria da Silva, CPF 123.456.789-09, "
            "deve revisar o documento."
        ),
        critica_adversarial="A testemunha João de Souza confirmou o fato.",
    )
    assert "123.456.789-09" not in (log.resposta or "")
    assert "Maria da Silva" not in (log.resposta or "")
    assert "João de Souza" not in (log.critica_adversarial or "")
    assert "[CPF_" in (log.resposta or "")


@pytest.mark.asyncio
async def test_context_builder_repassa_escopo_do_cliente_ao_rag(monkeypatch):
    from app.services.ai.core import context_builder
    from app.services import case_context, ai_service

    async def _dossie(_db, _case_id, sanitizar=True):
        return {"texto": "Dossiê sanitizado", "nomes_proteger": []}

    async def _escopo(_db, _case_id):
        return "cliente-escopo-1"

    capturado: dict = {}

    async def _buscar(_db, consulta, **kwargs):
        capturado["consulta"] = consulta
        capturado.update(kwargs)
        return []

    monkeypatch.setattr(case_context, "montar_dossie", _dossie)
    monkeypatch.setattr(ai_service, "_escopo_cliente_do_caso", _escopo)
    monkeypatch.setattr(ai_service, "buscar_contexto_rag", _buscar)

    ctx = await context_builder.montar_contexto(
        object(),
        mensagem="qual a tese aplicável?",
        case_id="caso-1",
        user=SimpleNamespace(id="u1"),
        usar_rag=True,
    )
    assert capturado["scope_client_id"] == "cliente-escopo-1"
    assert capturado["limite"] == 6
    assert "Dossiê sanitizado" in ctx.texto


def test_categoria_restrita_sem_cliente_e_bloqueada():
    from app.services.ingestion_service import _CATEGORIAS_RESTRITAS
    assert "precedente_interno" in _CATEGORIAS_RESTRITAS
    assert "comunicacao_processual" in _CATEGORIAS_RESTRITAS
