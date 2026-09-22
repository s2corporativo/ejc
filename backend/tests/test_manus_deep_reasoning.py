from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import manus_deep_reasoning as service


def _settings():
    return SimpleNamespace(
        AI_ENABLED=True,
        MANUS_ENABLED=True,
        MANUS_AUTO_ROUTING_ENABLED=False,
        AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        MANUS_API_KEY="test-key",
        MANUS_API_BASE_URL="https://api.manus.ai",
        MANUS_CONNECT_TIMEOUT=10.0,
        MANUS_READ_TIMEOUT=30.0,
        MANUS_WRITE_TIMEOUT=30.0,
        MANUS_MAX_INPUT_CHARS=16000,
        MANUS_AGENT_PROFILE="max",
        SECRET_KEY="x" * 64,
    )


def test_schema_structured_output_compativel():
    schema = service.MANUS_DEEP_SCHEMA
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(schema["required"])


def test_handle_e_vinculado_ao_usuario(monkeypatch):
    monkeypatch.setattr(service, "get_settings", _settings)
    h = service._handle("task-abc", "user-a")
    assert service._task_from_handle(h, "user-a") == "task-abc"
    with pytest.raises(HTTPException) as exc:
        service._task_from_handle(h, "user-b")
    assert exc.value.status_code == 404


def test_manus_nunca_pode_entrar_em_auto_routing(monkeypatch):
    s = _settings()
    s.MANUS_AUTO_ROUTING_ENABLED = True
    monkeypatch.setattr(service, "get_settings", lambda: s)
    with pytest.raises(HTTPException) as exc:
        service._settings_guard()
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_sigilo_reforcado_textual_bloqueia_manus(monkeypatch):
    monkeypatch.setattr(service, "get_settings", _settings)
    user = SimpleNamespace(id="u1", role="advogado")

    with pytest.raises(HTTPException) as exc:
        await service.iniciar_raciocinio(
            None,
            user=user,
            texto="Analise este caso envolvendo adolescente e possível abuso sexual.",
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_area_de_menores_bloqueia_manus(monkeypatch):
    monkeypatch.setattr(service, "get_settings", _settings)
    user = SimpleNamespace(id="u1", role="advogado")

    with pytest.raises(HTTPException) as exc:
        await service.iniciar_raciocinio(
            None,
            user=user,
            texto="Analise os fatos e as provas disponíveis para a estratégia.",
            area="infância e juventude",
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_criacao_pseudonimiza_antes_do_manus(monkeypatch):
    monkeypatch.setattr(service, "get_settings", _settings)
    captured = {}

    async def fake_create(self, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "task_id": "abc123", "task_url": "https://example.invalid/task"}

    monkeypatch.setattr(service.ManusClient, "create_task", fake_create)
    user = SimpleNamespace(id="u1", role="advogado")
    identificador = ".".join(("123", "456", "789")) + "-" + "09"
    out = await service.iniciar_raciocinio(
        None,
        user=user,
        texto=f"Analise profundamente o caso do cliente identificado por {identificador}.",
    )
    assert out["provider"] == "manus"
    assert identificador not in captured["content"]
    assert "[CPF_1]" in captured["content"]


@pytest.mark.asyncio
async def test_status_converte_structured_output_em_conteudo(monkeypatch):
    monkeypatch.setattr(service, "get_settings", _settings)
    handle = service._handle("task-xyz", "u1")

    async def fake_list(self, task_id):
        assert task_id == "task-xyz"
        return {
            "ok": True,
            "messages": [
                {
                    "type": "structured_output_result",
                    "structured_output_result": {
                        "success": True,
                        "value": {
                            "resumo_executivo": "Síntese.",
                            "questoes_juridicas": ["Questão A"],
                            "teses_possiveis": ["Tese A"],
                            "argumentos_contrarios": ["Risco A"],
                            "provas_necessarias": ["Prova A"],
                            "riscos": ["Risco B"],
                            "pontos_de_atencao": ["Ponto A"],
                            "informacoes_faltantes": ["Dado A"],
                            "proximos_passos": ["Passo A"],
                            "fontes_mencionadas": ["Fonte a conferir"],
                            "revisao_humana_obrigatoria": True,
                        },
                    },
                },
                {
                    "type": "status_update",
                    "status_update": {"agent_status": "stopped"},
                },
            ],
        }

    monkeypatch.setattr(service.ManusClient, "list_messages", fake_list)
    user = SimpleNamespace(id="u1", role="advogado")
    out = await service.consultar_raciocinio(user=user, handle=handle)
    assert out["status"] == "completed"
    assert "## Teses possíveis" in out["conteudo"]
    assert out["fontes"][0]["categoria"] == "manus_nao_verificada"
