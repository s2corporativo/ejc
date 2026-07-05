"""Fase 6 — integração do roteamento inteligente no ai_gateway + endpoint preview.

Contrato:
  - ROTEAMENTO off → cadeia atual por task_type intacta;
  - ROTEAMENTO on → provedor proposto vai à frente SE elegível;
  - roteador respeita elegibilidade: provedor externo bloqueado NÃO é escolhido;
  - custo estimado calculado na resposta do gateway;
  - endpoint preview exige JWT e reflete elegibilidade real.
"""
from __future__ import annotations

import inspect

import pytest

from app.core.config import get_settings
from app.services import ai_gateway as g


def _prep(monkeypatch, **kw):
    base = dict(
        ANTHROPIC_API_KEY="sk-x",
        ANTHROPIC_ENABLED=True,
        AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        AI_PROVIDER_PRIORITY="ollama,anthropic,groq",
        OLLAMA_ENABLED=True,
        GROQ_API_KEY="gk",
        ROTEAMENTO_INTELIGENTE_ENABLED=False,
        ROTEAMENTO_LIMIAR_MEDIO=3,
        ROTEAMENTO_LIMIAR_PESADO=6,
        ROTEAMENTO_PROVIDER_LEVE="groq",
        ROTEAMENTO_PROVIDER_MEDIO="ollama",
        ROTEAMENTO_PROVIDER_PESADO="anthropic",
    )
    base.update(kw)
    for k, v in base.items():
        monkeypatch.setattr(g.settings, k, v)


# ── _resolver_cadeia com provider_preferido ───────────────────────────────────

def test_cadeia_promove_preferido_elegivel(monkeypatch):
    _prep(monkeypatch)
    cadeia = g._resolver_cadeia(
        "elaboracao_peca", provider_force=None, model_override=None,
        provider_preferido="anthropic", model_preferido="claude-opus-4-8",
    )
    assert cadeia[0] == ("anthropic", "claude-opus-4-8")   # promovido à frente
    assert any(p == "ollama" for p, _ in cadeia)           # fallback preservado


def test_cadeia_ignora_preferido_inelegivel(monkeypatch):
    # Kill-switch de soberania: externos inelegíveis → anthropic proposto é ignorado.
    _prep(monkeypatch, AI_EXTERNAL_PROVIDERS_ALLOWED=False)
    cadeia = g._resolver_cadeia(
        "elaboracao_peca", provider_force=None, model_override=None,
        provider_preferido="anthropic", model_preferido="claude-opus-4-8",
    )
    assert all(p != "anthropic" for p, _ in cadeia)        # externo bloqueado fora
    assert cadeia[0][0] == "ollama"                        # cadeia normal


def test_cadeia_preferido_fora_do_task_routing_e_ignorado(monkeypatch):
    # 'resumo' não tem anthropic no TASK_ROUTING → não inventa provedor.
    _prep(monkeypatch)
    cadeia = g._resolver_cadeia(
        "resumo", provider_force=None, model_override=None,
        provider_preferido="anthropic", model_preferido="claude-opus-4-8",
    )
    assert all(p != "anthropic" for p, _ in cadeia)


# ── chat() on/off ─────────────────────────────────────────────────────────────

def _mock_provedor(monkeypatch, capture: dict):
    async def _fake(provider, model, messages, temperature, max_tokens):
        capture["provider"] = provider
        capture["model"] = model
        return "resposta", {"model": model or provider, "input_tokens": 100, "output_tokens": 200}
    monkeypatch.setattr(g, "_chamar_provedor", _fake)


async def test_chat_roteamento_off_usa_cadeia_por_task_type(monkeypatch):
    _prep(monkeypatch, ROTEAMENTO_INTELIGENTE_ENABLED=False)
    cap = {}
    _mock_provedor(monkeypatch, cap)
    resp = await g.chat([{"role": "user", "content": "oi"}], task_type="elaboracao_peca")
    # off → prioridade normal: ollama primeiro
    assert cap["provider"] == "ollama"
    assert resp.roteamento_tier is None


async def test_chat_roteamento_on_promove_provedor(monkeypatch):
    _prep(monkeypatch, ROTEAMENTO_INTELIGENTE_ENABLED=True)
    cap = {}
    _mock_provedor(monkeypatch, cap)
    # estrategia é tarefa pesada (peso 6) → tier pesado → anthropic proposto
    resp = await g.chat([{"role": "user", "content": "questão estratégica complexa"}],
                        task_type="estrategia")
    assert cap["provider"] == "anthropic"
    assert resp.roteamento_tier == "pesado"
    assert resp.roteamento_score is not None


async def test_chat_roteamento_on_respeita_kill_switch(monkeypatch):
    # Roteador propõe anthropic, mas externos bloqueados → cai p/ ollama local.
    _prep(monkeypatch, ROTEAMENTO_INTELIGENTE_ENABLED=True,
          AI_EXTERNAL_PROVIDERS_ALLOWED=False)
    cap = {}
    _mock_provedor(monkeypatch, cap)
    await g.chat([{"role": "user", "content": "peça"}], task_type="elaboracao_peca")
    assert cap["provider"] == "ollama"   # externo nunca escolhido


async def test_chat_calcula_custo_estimado(monkeypatch):
    _prep(monkeypatch, ROTEAMENTO_INTELIGENTE_ENABLED=False)
    cap = {}
    async def _fake(provider, model, messages, temperature, max_tokens):
        return "r", {"model": "claude-opus-4-8", "input_tokens": 1_000_000, "output_tokens": 0}
    monkeypatch.setattr(g, "_chamar_provedor", _fake)
    monkeypatch.setattr(g.settings, "AI_PROVIDER_PRIORITY", "anthropic,groq")
    monkeypatch.setattr(g.settings, "OLLAMA_ENABLED", False)
    resp = await g.chat([{"role": "user", "content": "x"}], task_type="estrategia")
    # Opus 4.8 = $5/1M input; 1M tokens input → $5 × USD_BRL (default 5.70) ≈ 28.5
    assert resp.custo_estimado_brl > 0


async def test_chat_override_desliga_roteamento(monkeypatch):
    # provider_override presente → roteamento não roda (sem tier).
    _prep(monkeypatch, ROTEAMENTO_INTELIGENTE_ENABLED=True)
    cap = {}
    _mock_provedor(monkeypatch, cap)
    resp = await g.chat([{"role": "user", "content": "x"}],
                        task_type="elaboracao_peca", provider_override="groq")
    assert cap["provider"] == "groq"
    assert resp.roteamento_tier is None


# ── Langfuse não quebra o fluxo (trace None) ─────────────────────────────────

async def test_chat_funciona_com_langfuse_desligado(monkeypatch):
    _prep(monkeypatch)
    monkeypatch.setattr(g.settings, "LANGFUSE_ENABLED", False)
    cap = {}
    _mock_provedor(monkeypatch, cap)
    resp = await g.chat([{"role": "user", "content": "x"}], task_type="resumo")
    assert resp.texto == "resposta"


# ── Endpoint preview ──────────────────────────────────────────────────────────

class TestEndpointRoteamentoPreview:
    def test_rota_registrada(self):
        from app.routers.ai import router
        rotas = {r.path: r for r in router.routes}
        assert "/ai/roteamento/preview" in rotas
        assert "GET" in rotas["/ai/roteamento/preview"].methods

    def test_endpoint_exige_jwt(self):
        from app.core.security import get_current_user
        from app.routers.ai import roteamento_preview
        params = inspect.signature(roteamento_preview).parameters
        assert params["cu"].default.dependency is get_current_user

    async def test_preview_retorna_tier_e_elegibilidade(self, monkeypatch):
        _prep(monkeypatch, ROTEAMENTO_INTELIGENTE_ENABLED=True)
        from app.routers.ai import roteamento_preview

        class _U:
            role = type("R", (), {"value": "admin"})()

        out = await roteamento_preview(task_type="estrategia", tamanho=100, cu=_U())
        assert out["tier"] == "pesado"
        assert out["provider_proposto"] == "anthropic"
        assert out["provider_elegivel"] is True
        assert out["roteamento_habilitado"] is True

    async def test_preview_reflete_inelegibilidade(self, monkeypatch):
        _prep(monkeypatch, ROTEAMENTO_INTELIGENTE_ENABLED=True,
              AI_EXTERNAL_PROVIDERS_ALLOWED=False)
        from app.routers.ai import roteamento_preview

        class _U:
            role = type("R", (), {"value": "admin"})()

        out = await roteamento_preview(task_type="estrategia", tamanho=100, cu=_U())
        assert out["provider_proposto"] == "anthropic"
        assert out["provider_elegivel"] is False  # kill-switch

    async def test_preview_403_para_papel_baixo(self, monkeypatch):
        # B2: introspecção de roteamento é restrita a sócio+ (mesmo gate do dossiê).
        _prep(monkeypatch, ROTEAMENTO_INTELIGENTE_ENABLED=True)
        from fastapi import HTTPException
        from app.routers.ai import roteamento_preview

        class _U:
            role = type("R", (), {"value": "estagiario"})()

        with pytest.raises(HTTPException) as exc:
            await roteamento_preview(task_type="estrategia", tamanho=100, cu=_U())
        assert exc.value.status_code == 403

    def test_preview_tem_rate_limit(self):
        # B2: a rota carrega uma dependência de rate limit (Depends(rate_limit(...))).
        from app.routers.ai import router
        rota = next(r for r in router.routes if r.path == "/ai/roteamento/preview")
        assert rota.dependencies, "preview deve ter dependência de rate limit"


# ── B1 — erro do provider no trace do Langfuse não ecoa PII/str(e) ────────────

async def test_erro_no_trace_nao_ecoa_pii(monkeypatch):
    _prep(monkeypatch, ROTEAMENTO_INTELIGENTE_ENABLED=False)

    async def _boom(provider, model, messages, temperature, max_tokens):
        # str(e) do provider carrega PII — não pode chegar ao Langfuse.
        raise RuntimeError("provider caiu: CPF 529.982.247-25 vazou no detalhe")

    monkeypatch.setattr(g, "_chamar_provedor", _boom)
    from app.services.observability import langfuse_client as _lf
    eventos: list = []
    monkeypatch.setattr(
        _lf, "registrar_evento",
        lambda trace, *, name, metadata: eventos.append((name, metadata)),
    )
    with pytest.raises(RuntimeError):
        await g.chat([{"role": "user", "content": "x"}], task_type="resumo")

    assert eventos, "deveria registrar evento de fallback"
    for name, meta in eventos:
        if not name.startswith("fallback:"):
            continue
        assert "529.982.247-25" not in str(meta)   # PII não vaza
        assert "vazou" not in str(meta)             # str(e) cru não vaza
        assert meta["erro"] == "RuntimeError"       # só a classe do erro
