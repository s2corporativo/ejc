from __future__ import annotations


def test_registry_externos_sao_suportados():
    from app.services.ai.provider_registry import PROVIDERS_EXTERNOS, PROVIDERS_SUPORTADOS
    assert PROVIDERS_EXTERNOS <= set(PROVIDERS_SUPORTADOS)
    assert [p for p in PROVIDERS_SUPORTADOS if p not in PROVIDERS_EXTERNOS] == ["ollama"]


def test_runtime_compartilha_registro():
    from app.main import app  # noqa: F401
    from app.services import ai_gateway, ai_skill_service
    from app.services.ai import adversarial, provider_policy, provider_registry

    assert ai_gateway._PROVIDERS_EXTERNOS is provider_registry.PROVIDERS_EXTERNOS
    assert ai_gateway._PROVIDERS_SUPORTADOS is provider_registry.PROVIDERS_SUPORTADOS
    assert provider_policy.PROVIDERS_EXTERNOS is provider_registry.PROVIDERS_EXTERNOS
    assert adversarial._PROVIDERS_CONHECIDOS is provider_registry.PROVIDERS_SUPORTADOS
    assert ai_skill_service._ENGINE_PROVIDER == {
        p: p for p in provider_registry.PROVIDERS_SUPORTADOS
    }


def test_kill_switch_bloqueia_externos(monkeypatch):
    from app.core.config import get_settings
    from app.services.ai.provider_registry import PROVIDERS_EXTERNOS, provider_elegivel

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_EXTERNAL_PROVIDERS_ALLOWED", False)
    monkeypatch.setattr(settings, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "x")
    monkeypatch.setattr(settings, "MARITACA_ENABLED", True)
    monkeypatch.setattr(settings, "MARITACA_API_KEY", "x")
    assert all(not provider_elegivel(p) for p in PROVIDERS_EXTERNOS)


def test_gateway_permanece_fail_closed(monkeypatch):
    from app.main import app  # noqa: F401
    from app.core.config import get_settings
    from app.services import ai_gateway

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_EXTERNAL_PROVIDERS_ALLOWED", False)
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", False)
    assert ai_gateway._resolver_cadeia("analise_juridica", None, None) == []


def test_kill_switch_global_bloqueia_todos_os_provedores(monkeypatch):
    """`AI_ENABLED=false` desliga TODO provedor, inclusive o local (AUD27-P0-1).

    A tabela de elegibilidade é a fonte única do kill-switch, mas checava só as
    flags POR PROVEDOR e a de externos — nunca `AI_ENABLED`. Como o caminho
    oficial do Núcleo Único (`/ai/core/*` → orchestrator.run → ai_gateway.chat
    → _provider_elegivel) passa por aqui, desligar a IA pela flag documentada
    não impedia a geração: com Ollama ligado (provedor local, sem chave), o
    endpoint continuava respondendo.
    """
    from app.core.config import get_settings
    from app.services.ai.provider_registry import PROVIDERS_SUPORTADOS, provider_elegivel

    settings = get_settings()
    # Tudo o que poderia habilitar um provedor está LIGADO — só o kill-switch
    # global está desligado. Se algum provedor sobrar elegível, o defeito voltou.
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(settings, "GROQ_ENABLED", True)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "x")
    monkeypatch.setattr(settings, "MARITACA_ENABLED", True)
    monkeypatch.setattr(settings, "MARITACA_API_KEY", "x")

    assert all(not provider_elegivel(p) for p in PROVIDERS_SUPORTADOS)


def test_kill_switch_global_esvazia_a_cadeia_do_gateway(monkeypatch):
    """Consequência no gateway: sem provedor elegível a cadeia fica vazia e a
    chamada falha ANTES de tocar rede — é o fail-closed que `/ai/core/*` herda."""
    from app.main import app  # noqa: F401
    from app.core.config import get_settings
    from app.services import ai_gateway

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)

    assert ai_gateway._resolver_cadeia("analise_juridica", None, None) == []
    # E o provider forçado também não escapa pelo atalho de `provider_force`.
    assert ai_gateway._resolver_cadeia("analise_juridica", "ollama", None) == []
    assert ai_gateway.ia_disponivel() is False


def test_motivo_inelegivel_nomeia_o_kill_switch_global(monkeypatch):
    """O painel de governança precisa distinguir kill-switch global de chave
    ausente — é a razão de existir da tabela de requisitos."""
    from app.core.config import get_settings
    from app.services.ai.provider_registry import motivo_inelegivel

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)

    assert "AI_ENABLED=false" in (motivo_inelegivel("ollama") or "")


def test_mensagem_de_bloqueio_da_policy_aponta_o_kill_switch(monkeypatch):
    """Com `AI_ENABLED=false` a cadeia esvazia — e a mensagem tem que dizer POR QUÊ.

    A `provider_policy` só sabia duas causas de cadeia vazia (PII residual ou
    deploy sem provedor) e, na dúvida, mandava configurar `ANTHROPIC_API_KEY`.
    Depois do AUD27-P0-1 existe uma terceira, e ela é a única em que nenhuma
    chave resolve: o operador perseguiria a causa errada.
    """
    from app.core.config import get_settings
    from app.services.ai.provider_policy import AIProviderPolicy

    settings = get_settings()
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    monkeypatch.setattr(settings, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "x")

    d = AIProviderPolicy().avaliar("texto sem dado pessoal", "analise_juridica")

    assert d.permitido is False
    assert "AI_ENABLED" in (d.bloqueio_motivo or "")
    assert "ANTHROPIC_API_KEY" not in (d.bloqueio_motivo or "")
