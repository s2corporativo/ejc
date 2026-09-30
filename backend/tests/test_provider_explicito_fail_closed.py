"""Escolha explícita não autoriza fallback para outro destino (#1771)."""
from unittest.mock import AsyncMock

import pytest

from app.core.ai_errors import SafeAIError
from app.services import ai_cache, ai_gateway as gateway


@pytest.mark.parametrize("provider", ["ollama", "groq", "maritaca", "anthropic"])
@pytest.mark.parametrize("rollback", [False, True])
@pytest.mark.parametrize("task", ["resumo", "analise_juridica"])
async def test_escolha_inelegivel_bloqueia_antes_de_cache_e_rede(
    monkeypatch, provider, rollback, task,
):
    monkeypatch.setattr(gateway.settings, "AI_PROVIDER", "auto")
    monkeypatch.setattr(gateway.settings, "ANTHROPIC_AUTO_ROUTING_ENABLED", rollback)
    monkeypatch.setattr(gateway, "_provider_elegivel", lambda p: p != provider)
    cache = AsyncMock(return_value=None)
    chamada = AsyncMock(side_effect=AssertionError("provedor não autorizado"))
    monkeypatch.setattr(ai_cache, "obter", cache)
    monkeypatch.setattr(gateway, "_chamar_provedor", chamada)
    # Métrica de política: o bloqueio precisa aparecer em
    # /ia-governanca/provedores (review P2 da #1869 — antes ficava "0 falhas").
    from app.services.ai import provider_metrics_runtime
    bloqueio = AsyncMock(return_value=None)
    monkeypatch.setattr(provider_metrics_runtime, "registrar_bloqueio_politica", bloqueio)

    with pytest.raises(SafeAIError) as erro:
        await gateway.chat(
            [{"role": "user", "content": "Texto sintético para teste de roteamento."}],
            task_type=task,
            provider_override=provider,
        )

    assert erro.value.ai_error_code == "no_provider"
    cache.assert_not_awaited()
    chamada.assert_not_awaited()
    bloqueio.assert_awaited_once()
    assert bloqueio.await_args.kwargs["motivo"] == f"provider_forcado_inelegivel:{provider}"
    assert bloqueio.await_args.kwargs["task_type"] == task


@pytest.mark.parametrize("provider", ["ollama", "groq", "maritaca", "anthropic"])
def test_escolha_elegivel_mantem_apenas_o_destino_solicitado(monkeypatch, provider):
    monkeypatch.setattr(gateway, "_provider_elegivel", lambda p: True)
    cadeia = gateway._resolver_cadeia("analise_juridica", provider, None)
    assert [p for p, _ in cadeia] == [provider]


@pytest.mark.parametrize("task,esperado", [("resumo", "groq"), ("analise_juridica", "maritaca")])
def test_automatico_preserva_afinidade_e_fallback_local(monkeypatch, task, esperado):
    monkeypatch.setattr(gateway.settings, "ANTHROPIC_AUTO_ROUTING_ENABLED", False)
    monkeypatch.setattr(gateway, "_provider_elegivel", lambda p: True)
    cadeia = gateway._resolver_cadeia(task, None, None)
    assert [p for p, _ in cadeia] == [esperado, "ollama"]
