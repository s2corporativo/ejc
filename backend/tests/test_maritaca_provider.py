"""Integração Maritaca AI (Sabiá) — provider BR OpenAI-compatible + wiring no
AI Gateway / policy / cost / adversarial.

Tudo mockado (httpx nunca toca a rede). Settings via monkeypatch nos atributos
da instância cacheada de get_settings() — mesmo padrão de test_duas_ias.py.
"""
from __future__ import annotations

import httpx
import pytest

from app.core.config import get_settings


# ── Fixture base: Maritaca elegível, externos permitidos ──────────────────────
@pytest.fixture
def s(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "MARITACA_ENABLED", True)
    monkeypatch.setattr(st, "MARITACA_API_KEY", "mtk-fake-para-testes")
    monkeypatch.setattr(st, "MARITACA_BASE_URL", "https://chat.maritaca.ai/api")
    monkeypatch.setattr(st, "MARITACA_MODEL_COMPLEXO", "sabia-4")
    monkeypatch.setattr(st, "MARITACA_MODEL_RAPIDO", "sabiazinho-4")
    monkeypatch.setattr(st, "MARITACA_MAX_TOKENS", 8000)
    monkeypatch.setattr(st, "MARITACA_TIMEOUT", 120)
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(st, "AI_PROVIDER_PRIORITY", "ollama,anthropic,maritaca,groq")
    monkeypatch.setattr(st, "AI_PROVIDER", "auto")
    return st


# ── Fake httpx.AsyncClient ────────────────────────────────────────────────────
def _resp_openai(texto="Resposta jurídica fictícia.", *, prompt=7, completion=13,
                 model="sabia-4", status=200, body=None):
    data = body if body is not None else {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": texto}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }

    class _Resp:
        status_code = status

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "erro", request=httpx.Request("POST", "https://x"), response=self,
                )

        def json(self):
            return data

    return _Resp()


def _fake_client_factory(resp, capture: dict | None = None, *, raise_exc=None):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            if capture is not None:
                capture.update({"url": url, "json": json, "headers": headers})
            if raise_exc is not None:
                raise raise_exc
            return resp

    return _Client


# ══════════════════════════════════════════════════════════════════════════════
# 1. Provider maritaca — chat() e health()
# ══════════════════════════════════════════════════════════════════════════════
class TestProviderChat:
    async def test_sucesso_retorna_texto_e_usage(self, s, monkeypatch):
        from app.services.providers import maritaca_provider
        cap: dict = {}
        monkeypatch.setattr(
            maritaca_provider.httpx, "AsyncClient",
            _fake_client_factory(_resp_openai(), cap),
        )
        texto, usage = await maritaca_provider.chat(
            [{"role": "user", "content": "olá"}], model="sabia-4",
        )
        assert texto == "Resposta jurídica fictícia."
        assert usage == {
            "input_tokens": 7, "output_tokens": 13,
            "model": "sabia-4", "provider": "maritaca",
        }
        # Endpoint OpenAI-compatible + Bearer auth + payload correto.
        assert cap["url"] == "https://chat.maritaca.ai/api/chat/completions"
        assert cap["headers"]["Authorization"] == "Bearer mtk-fake-para-testes"
        assert cap["json"]["model"] == "sabia-4"
        assert cap["json"]["stream"] is False

    async def test_default_model_quando_sem_model(self, s, monkeypatch):
        from app.services.providers import maritaca_provider
        cap: dict = {}
        monkeypatch.setattr(
            maritaca_provider.httpx, "AsyncClient",
            _fake_client_factory(_resp_openai(model="sabia-4"), cap),
        )
        await maritaca_provider.chat([{"role": "user", "content": "x"}])
        assert cap["json"]["model"] == "sabia-4"  # MARITACA_MODEL_COMPLEXO

    async def test_max_tokens_capado_pelo_teto(self, s, monkeypatch):
        from app.services.providers import maritaca_provider
        monkeypatch.setattr(s, "MARITACA_MAX_TOKENS", 500)
        cap: dict = {}
        monkeypatch.setattr(
            maritaca_provider.httpx, "AsyncClient",
            _fake_client_factory(_resp_openai(), cap),
        )
        await maritaca_provider.chat(
            [{"role": "user", "content": "x"}], max_tokens=999_999,
        )
        assert cap["json"]["max_tokens"] == 500

    async def test_sem_chave_levanta(self, s, monkeypatch):
        from app.services.providers import maritaca_provider
        monkeypatch.setattr(s, "MARITACA_API_KEY", "")
        with pytest.raises(RuntimeError, match="MARITACA_API_KEY"):
            await maritaca_provider.chat([{"role": "user", "content": "x"}])

    async def test_desabilitado_levanta(self, s, monkeypatch):
        from app.services.providers import maritaca_provider
        monkeypatch.setattr(s, "MARITACA_ENABLED", False)
        with pytest.raises(RuntimeError, match="desabilitado"):
            await maritaca_provider.chat([{"role": "user", "content": "x"}])

    async def test_http_error_vira_runtimeerror_curto_sem_corpo(self, s, monkeypatch):
        from app.services.providers import maritaca_provider
        # corpo com "eco" do prompt NÃO pode vazar na mensagem de erro.
        resp = _resp_openai(status=429, body={"error": "SEGREDO_ECOADO"})
        monkeypatch.setattr(
            maritaca_provider.httpx, "AsyncClient",
            _fake_client_factory(resp),
        )
        with pytest.raises(RuntimeError) as ei:
            await maritaca_provider.chat([{"role": "user", "content": "x"}])
        msg = str(ei.value)
        assert "429" in msg
        assert "SEGREDO_ECOADO" not in msg
        assert "mtk-fake-para-testes" not in msg  # chave nunca vaza

    async def test_timeout_vira_runtimeerror(self, s, monkeypatch):
        from app.services.providers import maritaca_provider
        monkeypatch.setattr(
            maritaca_provider.httpx, "AsyncClient",
            _fake_client_factory(None, raise_exc=httpx.TimeoutException("slow")),
        )
        with pytest.raises(RuntimeError, match="timeout"):
            await maritaca_provider.chat([{"role": "user", "content": "x"}])

    async def test_resposta_vazia_levanta(self, s, monkeypatch):
        from app.services.providers import maritaca_provider
        resp = _resp_openai(body={"choices": []})
        monkeypatch.setattr(
            maritaca_provider.httpx, "AsyncClient",
            _fake_client_factory(resp),
        )
        with pytest.raises(RuntimeError, match="vazia"):
            await maritaca_provider.chat([{"role": "user", "content": "x"}])


class TestProviderHealth:
    async def test_health_true_com_chave_e_enabled(self, s):
        from app.services.providers import maritaca_provider
        assert await maritaca_provider.health() is True

    async def test_health_false_sem_chave(self, s, monkeypatch):
        from app.services.providers import maritaca_provider
        monkeypatch.setattr(s, "MARITACA_API_KEY", "")
        assert await maritaca_provider.health() is False

    async def test_health_false_desabilitado(self, s, monkeypatch):
        from app.services.providers import maritaca_provider
        monkeypatch.setattr(s, "MARITACA_ENABLED", False)
        assert await maritaca_provider.health() is False


# ══════════════════════════════════════════════════════════════════════════════
# 2. AI Gateway — elegibilidade, cadeia e barreira externa
# ══════════════════════════════════════════════════════════════════════════════
class TestGatewayWiring:
    def test_maritaca_e_provider_externo(self):
        from app.services.ai_gateway import _PROVIDERS_EXTERNOS
        assert "maritaca" in _PROVIDERS_EXTERNOS  # passa pela barreira LGPD

    def test_elegivel_com_chave_enabled_e_externos_ok(self, s):
        from app.services.ai_gateway import _provider_elegivel
        assert _provider_elegivel("maritaca") is True

    def test_inelegivel_sem_chave(self, s, monkeypatch):
        from app.services.ai_gateway import _provider_elegivel
        monkeypatch.setattr(s, "MARITACA_API_KEY", "")
        assert _provider_elegivel("maritaca") is False

    def test_inelegivel_quando_externos_bloqueados(self, s, monkeypatch):
        from app.services.ai_gateway import _provider_elegivel
        monkeypatch.setattr(s, "AI_EXTERNAL_PROVIDERS_ALLOWED", False)
        assert _provider_elegivel("maritaca") is False

    def test_cadeia_inclui_maritaca_antes_do_groq(self, s, monkeypatch):
        # ollama OFF, anthropic sem chave → sobram maritaca e groq.
        from app.services.ai_gateway import _resolver_cadeia
        monkeypatch.setattr(s, "OLLAMA_ENABLED", False)
        monkeypatch.setattr(s, "ANTHROPIC_ENABLED", False)
        monkeypatch.setattr(s, "GROQ_API_KEY", "gsk-fake")
        cadeia = [p for p, _ in _resolver_cadeia("elaboracao_peca", None, None)]
        assert "maritaca" in cadeia and "groq" in cadeia
        # prioridade "…,maritaca,groq" → maritaca vem antes.
        assert cadeia.index("maritaca") < cadeia.index("groq")

    def test_provider_force_maritaca(self, s):
        from app.services.ai_gateway import _resolver_cadeia
        cadeia = _resolver_cadeia("elaboracao_peca", "maritaca", None)
        assert cadeia == [("maritaca", "sabia-4")]

    def test_resolver_modelo_complexo_vs_rapido(self, s):
        from app.services.ai_gateway import _resolver_modelo
        assert _resolver_modelo("maritaca", "elaboracao_peca", None) == "sabia-4"
        assert _resolver_modelo("maritaca", "resumo", None) == "sabiazinho-4"

    def test_tarefa_leve_nao_roteia_maritaca(self, s, monkeypatch):
        # resumo/chat_rapido são econômicas: só ollama→groq (sem maritaca).
        from app.services.ai_gateway import TASK_ROUTING
        assert "maritaca" not in [p for p, _ in TASK_ROUTING["resumo"]]
        assert "maritaca" not in [p for p, _ in TASK_ROUTING["chat_rapido"]]

    async def test_health_reporta_maritaca(self, s, monkeypatch):
        # OLLAMA/GROQ off para o health não tocar a rede (hermético).
        monkeypatch.setattr(s, "OLLAMA_ENABLED", False)
        monkeypatch.setattr(s, "GROQ_API_KEY", "")
        from app.services import ai_gateway
        h = await ai_gateway.health()
        assert "maritaca" in h and h["maritaca"]["modelo"] == "sabia-4"


# ══════════════════════════════════════════════════════════════════════════════
# 3. Custo (BRL nativo, tabela por-modelo)
# ══════════════════════════════════════════════════════════════════════════════
class TestCusto:
    def test_preco_sabia4_por_milhao(self):
        from app.services.ai_cost import estimar_custo_brl
        # 1M input × R$5 + 1M output × R$10 = R$15.
        custo = estimar_custo_brl("maritaca", 1_000_000, 1_000_000, "sabia-4")
        assert float(custo) == pytest.approx(15.0)

    def test_preco_sabiazinho4_mais_barato(self):
        from app.services.ai_cost import estimar_custo_brl
        # 1M × R$1 + 1M × R$4 = R$5.
        custo = estimar_custo_brl("maritaca", 1_000_000, 1_000_000, "sabiazinho-4")
        assert float(custo) == pytest.approx(5.0)

    def test_modelo_desconhecido_usa_defaults_de_config(self, s):
        from app.services.ai_cost import estimar_custo_brl
        # Modelo fora da tabela → defaults MARITACA_PRECO_*_BRL_POR_MILHAO (5/10).
        custo = estimar_custo_brl("maritaca", 1_000_000, 0, "sabia-99-nao-existe")
        assert float(custo) == pytest.approx(5.0)

    def test_sem_conversao_usd(self, monkeypatch):
        # Maritaca é BRL nativo: USD_BRL_RATE não afeta o custo.
        import os
        from app.services.ai_cost import estimar_custo_brl
        monkeypatch.setitem(os.environ, "USD_BRL_RATE", "999")
        custo = estimar_custo_brl("maritaca", 1_000_000, 0, "sabia-4")
        assert float(custo) == pytest.approx(5.0)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Modo Duas IAs — Maritaca como provider DIVERSO elegível
# ══════════════════════════════════════════════════════════════════════════════
class TestAdversarialDiverso:
    def test_maritaca_e_provider_conhecido(self):
        from app.services.ai.adversarial import _PROVIDERS_CONHECIDOS
        assert "maritaca" in _PROVIDERS_CONHECIDOS

    def test_origem_anthropic_pode_cair_em_maritaca(self, s, monkeypatch):
        from app.services.ai.adversarial import escolher_provider_diverso
        # Só maritaca elegível (ollama off, anthropic/groq sem chave).
        monkeypatch.setattr(s, "OLLAMA_ENABLED", False)
        monkeypatch.setattr(s, "ANTHROPIC_ENABLED", False)
        monkeypatch.setattr(s, "GROQ_API_KEY", "")
        assert escolher_provider_diverso("anthropic") == "maritaca"
