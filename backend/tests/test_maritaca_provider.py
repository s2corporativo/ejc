"""Testes do provider Maritaca (Sabiá) — jurídico automático, externo (LGPD).

Sem rede: a única função de I/O (`_post`) é mockada; settings via monkeypatch
na instância cacheada de get_settings() (mesmo padrão de test_agente_ia).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import get_settings
from app.services import ai_cost, ai_gateway
from app.services.ai import provider_policy
from app.services.providers import maritaca_provider


@pytest.fixture
def habilitado(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "MARITACA_ENABLED", True, raising=False)
    monkeypatch.setattr(st, "MARITACA_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(st, "MARITACA_MODEL", "sabia-4", raising=False)
    monkeypatch.setattr(st, "MARITACA_MODEL_RAPIDO", "sabiazinho-4", raising=False)
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True, raising=False)
    return st


_FAKE_OK = {
    "model": "sabia-4",
    "choices": [{"message": {"content": "Olá, sou a Sabiá."}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46},
}


@pytest.mark.asyncio
async def test_chat_parseia_texto_e_usage(monkeypatch, habilitado):
    async def _fake_post(payload):
        # contrato OpenAI-compatible enviado corretamente
        assert payload["model"] == "sabia-4"
        assert payload["messages"][0]["content"] == "oi"
        return _FAKE_OK

    monkeypatch.setattr(maritaca_provider, "_post", _fake_post)
    texto, usage = await maritaca_provider.chat(
        [{"role": "user", "content": "oi"}], None, 0.2, 512
    )
    assert texto == "Olá, sou a Sabiá."
    assert usage["input_tokens"] == 12
    assert usage["output_tokens"] == 34
    assert usage["provider"] == "maritaca"


@pytest.mark.asyncio
async def test_chat_tools_normaliza_para_contrato_anthropic(monkeypatch, habilitado):
    resp_tool = {
        "model": "sabia-4",
        "choices": [{
            "message": {
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {
                        "name": "buscar_precedentes",
                        "arguments": '{"consulta": "dano moral"}',
                    },
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7},
    }

    async def _fake_post(payload):
        return resp_tool

    monkeypatch.setattr(maritaca_provider, "_post", _fake_post)
    out = await maritaca_provider.chat_tools(
        [{"role": "user", "content": "x"}], None, 256, []
    )
    assert out["stop_reason"] == "tool_use"
    assert out["tool_calls"][0]["name"] == "buscar_precedentes"
    assert out["tool_calls"][0]["input"] == {"consulta": "dano moral"}
    # resposta sem tool → end_turn
    monkeypatch.setattr(maritaca_provider, "_post", lambda payload: _async_ret(_FAKE_OK))
    out2 = await maritaca_provider.chat_tools([{"role": "user", "content": "x"}], None, 256, [])
    assert out2["stop_reason"] == "end_turn"
    # finish_reason "length" (truncado) → max_tokens, nao mascarado como end_turn
    resp_len = {
        "model": "sabia-4",
        "choices": [{"message": {"content": "..."}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    monkeypatch.setattr(maritaca_provider, "_post", lambda payload: _async_ret(resp_len))
    out3 = await maritaca_provider.chat_tools([{"role": "user", "content": "x"}], None, 8, [])
    assert out3["stop_reason"] == "max_tokens"


async def _async_ret(v):
    return v


def test_maritaca_e_provider_externo_em_ambos_os_registros():
    # Externo em AMBOS os pontos → passa pela barreira LGPD do gateway.
    assert "maritaca" in ai_gateway._PROVIDERS_EXTERNOS
    assert "maritaca" in provider_policy.PROVIDERS_EXTERNOS


def test_desabilitado_nao_elegivel_e_fora_da_cadeia(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "MARITACA_ENABLED", False, raising=False)
    monkeypatch.setattr(st, "MARITACA_API_KEY", "", raising=False)
    # Kill-switch explícito: desligada fica inelegível e ausente da cadeia.
    assert ai_gateway._provider_elegivel("maritaca") is False
    cadeia = ai_gateway._resolver_cadeia("elaboracao_peca", None, None)
    assert "maritaca" not in [p for p, _ in cadeia]


def test_habilitado_com_chave_fica_elegivel(habilitado):
    assert ai_gateway._provider_elegivel("maritaca") is True


# ── Reorganização IA jurídica (2026-07-19): Maritaca no caminho jurídico ─────

def test_habilitada_entra_nas_cadeias_juridicas_antes_do_groq(monkeypatch, habilitado):
    monkeypatch.setattr(habilitado, "AI_PROVIDER_PRIORITY", "ollama,anthropic,maritaca,groq")
    monkeypatch.setattr(habilitado, "GROQ_API_KEY", "groq-key", raising=False)
    for task in ("analise_juridica", "estrategia", "analise_contrato",
                 "auditoria_peca", "jurimetria", "critica_adversarial",
                 "elaboracao_peca"):
        provedores = [p for p, _ in ai_gateway._resolver_cadeia(task, None, None)]
        assert "maritaca" in provedores, task
        assert provedores.index("maritaca") < provedores.index("groq"), task


def test_provider_force_maritaca_honrado(habilitado):
    cadeia = ai_gateway._resolver_cadeia("analise_juridica", "maritaca", None)
    assert cadeia == [("maritaca", "sabia-4")]


def test_provider_force_maritaca_inelegivel_cai_na_cadeia_automatica(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "MARITACA_ENABLED", False, raising=False)
    monkeypatch.setattr(st, "MARITACA_API_KEY", "", raising=False)
    cadeia = ai_gateway._resolver_cadeia("analise_juridica", "maritaca", None)
    assert all(p != "maritaca" for p, _ in cadeia)  # não falha duro; roteia normal


def test_roteamento_inteligente_promove_maritaca(monkeypatch, habilitado):
    monkeypatch.setattr(habilitado, "AI_PROVIDER_PRIORITY", "ollama,anthropic,maritaca,groq")
    cadeia = ai_gateway._resolver_cadeia(
        "elaboracao_peca", None, None,
        provider_preferido="maritaca", model_preferido="sabia-4",
    )
    assert cadeia[0] == ("maritaca", "sabia-4")


def test_model_router_diferencia_tier_maritaca(habilitado):
    from app.services.ai.model_router import _model_do_provider
    assert _model_do_provider("maritaca", "pesado") == "sabia-4"
    # médio NÃO rebaixa (anti-rebaixamento P1, espelha o anthropic): usa o modelo
    # de qualidade, não o rápido.
    assert _model_do_provider("maritaca", "medio") == "sabia-4"
    assert _model_do_provider("maritaca", "leve") == "sabiazinho-4"


def test_adversarial_escolhe_maritaca_como_provider_diverso(monkeypatch, habilitado):
    # Só a Maritaca elegível e diferente da origem → diversidade real de
    # laboratório na crítica (Duas IAs), mesmo fora de AI_PROVIDER_PRIORITY.
    from app.services.ai.adversarial import escolher_provider_diverso
    monkeypatch.setattr(habilitado, "AI_PROVIDER_PRIORITY", "ollama,anthropic,groq")
    monkeypatch.setattr(habilitado, "OLLAMA_ENABLED", False, raising=False)
    monkeypatch.setattr(habilitado, "ANTHROPIC_ENABLED", False, raising=False)
    monkeypatch.setattr(habilitado, "GROQ_API_KEY", "", raising=False)
    assert escolher_provider_diverso("anthropic") == "maritaca"


def test_policy_prioriza_maritaca_em_tarefa_complexa_sem_anthropic(monkeypatch, habilitado):
    monkeypatch.setattr(habilitado, "AI_PROVIDER_PRIORITY", "ollama,anthropic,maritaca,groq")
    monkeypatch.setattr(habilitado, "OLLAMA_ENABLED", False, raising=False)
    monkeypatch.setattr(habilitado, "ANTHROPIC_ENABLED", False, raising=False)
    monkeypatch.setattr(habilitado, "GROQ_API_KEY", "groq-key", raising=False)
    decisao = provider_policy.AIProviderPolicy().avaliar(
        "qual a tese aplicavel ao caso?", "analise_juridica"
    )
    assert decisao.permitido is True
    assert decisao.provider_chain[0][0] == "maritaca"
    assert "Maritaca" in decisao.motivo


def test_preco_em_brl_positivo_e_correto():
    # sabia-4: 5 (in) + 20 (out) por 1M = R$ 25 para 1M+1M.
    assert ai_cost.estimar_custo_brl("maritaca", 1_000_000, 1_000_000, "sabia-4") == Decimal("25.000000")
    # sabiazinho-4: 1 + 4 = R$ 5.
    assert ai_cost.estimar_custo_brl("maritaca", 1_000_000, 1_000_000, "sabiazinho-4") == Decimal("5.000000")
    # br-sp = +30% (só input, 1M): 5 * 1.3 = 6.5.
    assert ai_cost.estimar_custo_brl("maritaca", 1_000_000, 0, "sabia-4-br-sp") == Decimal("6.500000")
    # modelo desconhecido → 0 (nunca levanta).
    assert ai_cost.estimar_custo_brl("maritaca", 1_000_000, 1_000_000, "inexistente") == Decimal("0.000000")
