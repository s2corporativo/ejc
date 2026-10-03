"""Regressão — núcleo de IA (auditoria de 03/10/2026).

NIA-05  chat_agentico aplica o piso de sigilo da TAREFA mesmo com modo explícito.
NIA-06  cache decide pelo modo EFETIVO da chamada, não só pela tarefa.
NIA-07  falha do grounding ao vivo torna a revisão humana obrigatória.
"""
from __future__ import annotations

import pytest


# ── NIA-05 ────────────────────────────────────────────────────────────────────

async def test_chat_agentico_nao_rebaixa_tarefa_de_sigilo_reforcado(monkeypatch):
    """task_type de sigilo reforçado + modo explícito mais fraco → bloqueio
    seguro, sem chamar o provider externo."""
    from app.core.ai_errors import SafeAIError
    from app.services import ai_gateway
    from app.services.ai.sanitization_policy import ModoSanitizacao
    from app.services.providers import anthropic_provider

    s = ai_gateway.settings
    monkeypatch.setattr(s, "AI_AGENT_PROVIDER", "anthropic", raising=False)
    monkeypatch.setattr(ai_gateway, "_provider_elegivel", lambda p: p == "anthropic")
    chamado = []

    async def _nao_pode(*a, **k):
        chamado.append(True)
        return {"text": "x", "tool_calls": [], "usage": {}}

    monkeypatch.setattr(anthropic_provider, "chat_tools", _nao_pode)
    with pytest.raises(SafeAIError) as exc:
        await ai_gateway.chat_agentico(
            [{"role": "user", "content": "fatos"}], tools=[],
            task_type="crimes_sexuais",
            modo_sanitizacao=ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
        )
    assert exc.value.ai_error_code == "sigilo_blocked"
    assert not chamado


# ── NIA-06 ────────────────────────────────────────────────────────────────────

def test_cache_respeita_modo_efetivo_do_caso(monkeypatch):
    from app.services import ai_cache
    from app.services.ai.sanitization_policy import ModoSanitizacao

    monkeypatch.setattr(ai_cache, "_tarefa_cacheavel", lambda t: True)  # override → mascaramento
    msgs = [{"role": "user", "content": "x"}]
    assert ai_cache.chave("resumo", msgs).startswith("ai:resp:")
    assert ai_cache.chave(
        "resumo", msgs, modo_sanitizacao=ModoSanitizacao.MASCARAMENTO,
    ).startswith("ai:resp:")
    for modo in (ModoSanitizacao.LOCAL_COMPLETO,
                 ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
                 ModoSanitizacao.EXTRACAO_LOCAL):
        assert ai_cache.chave("resumo", msgs, modo_sanitizacao=modo).startswith(
            "ai:nocache:"), modo


# ── NIA-07 ────────────────────────────────────────────────────────────────────

async def test_falha_do_grounding_exige_revisao(monkeypatch):
    from app.services import citation_check, citation_gate, verificador_jurisprudencia
    from app.services.ai.core import response_validator

    monkeypatch.setattr(citation_gate, "politica_citacoes", lambda: "marcar")
    monkeypatch.setattr(citation_gate, "avaliar_bloqueantes", lambda c: [])

    async def _cit(db, conteudo):
        return {"confirmadas": 1, "nao_encontradas": 0}

    async def _falha(*a, **k):
        raise RuntimeError("indisponível")

    monkeypatch.setattr(citation_check, "verificar_citacoes", _cit)
    monkeypatch.setattr(verificador_jurisprudencia, "verificar_jurisprudencia", _falha)
    r = await response_validator.validar(
        object(), "Conforme a Súmula 297 do STJ.", exige_fonte=True,
        fontes=[{"id": 1}],
    )
    assert any("Grounding ao vivo" in a for a in r["alertas"])
    assert r["revisao_obrigatoria"] is True
