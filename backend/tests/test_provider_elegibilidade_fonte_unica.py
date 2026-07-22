"""Regressão: elegibilidade de provedor tem FONTE ÚNICA.

Garante que os três pontos de consulta de elegibilidade concordam byte-a-byte
em qualquer configuração — sem drift entre as cópias estáticas:

    ai_gateway._provider_elegivel(p)
      == AIProviderPolicy._elegivel(p)
      == provider_registry.provider_elegivel(p)

Após a refatoração, os dois primeiros DELEGAM ao terceiro (a fonte única).
`provider_registry_runtime.instalar()` continua reatribuindo os símbolos à mesma
função — este teste confirma que a igualdade vale ANTES e DEPOIS do install
(idempotente). Sem rede: settings via monkeypatch nos ATRIBUTOS da instância
cacheada de get_settings() (lru_cache), mesmo padrão de test_provider_registry.
"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services import ai_gateway
from app.services.ai import provider_registry
from app.services.ai.provider_policy import AIProviderPolicy

PROVIDERS = ("ollama", "anthropic", "groq", "maritaca")

# (nome do cenário, overrides de settings, elegibilidade esperada por provedor)
CENARIOS = [
    (
        "tudo_desligado",
        dict(
            OLLAMA_ENABLED=False,
            ANTHROPIC_ENABLED=False, ANTHROPIC_API_KEY="",
            GROQ_API_KEY="",
            MARITACA_ENABLED=False, MARITACA_API_KEY="",
            AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        ),
        dict(ollama=False, anthropic=False, groq=False, maritaca=False),
    ),
    (
        "somente_ollama_local",
        dict(
            OLLAMA_ENABLED=True,
            ANTHROPIC_ENABLED=False, ANTHROPIC_API_KEY="",
            GROQ_API_KEY="",
            MARITACA_ENABLED=False, MARITACA_API_KEY="",
            AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        ),
        dict(ollama=True, anthropic=False, groq=False, maritaca=False),
    ),
    (
        "anthropic_habilitado_com_chave",
        dict(
            OLLAMA_ENABLED=False,
            ANTHROPIC_ENABLED=True, ANTHROPIC_API_KEY="sk-ant-fake",
            GROQ_API_KEY="",
            MARITACA_ENABLED=False, MARITACA_API_KEY="",
            AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        ),
        dict(ollama=False, anthropic=True, groq=False, maritaca=False),
    ),
    (
        "anthropic_com_chave_mas_enabled_off",
        dict(
            OLLAMA_ENABLED=False,
            ANTHROPIC_ENABLED=False, ANTHROPIC_API_KEY="sk-ant-fake",
            GROQ_API_KEY="",
            MARITACA_ENABLED=False, MARITACA_API_KEY="",
            AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        ),
        dict(ollama=False, anthropic=False, groq=False, maritaca=False),
    ),
    (
        "groq_com_chave",
        dict(
            OLLAMA_ENABLED=False,
            ANTHROPIC_ENABLED=False, ANTHROPIC_API_KEY="",
            GROQ_API_KEY="gsk-fake",
            MARITACA_ENABLED=False, MARITACA_API_KEY="",
            AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        ),
        dict(ollama=False, anthropic=False, groq=True, maritaca=False),
    ),
    (
        "maritaca_habilitada_com_chave",
        dict(
            OLLAMA_ENABLED=False,
            ANTHROPIC_ENABLED=False, ANTHROPIC_API_KEY="",
            GROQ_API_KEY="",
            MARITACA_ENABLED=True, MARITACA_API_KEY="mrt-fake",
            AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        ),
        dict(ollama=False, anthropic=False, groq=False, maritaca=True),
    ),
    (
        "maritaca_habilitada_sem_chave",
        dict(
            OLLAMA_ENABLED=False,
            ANTHROPIC_ENABLED=False, ANTHROPIC_API_KEY="",
            GROQ_API_KEY="",
            MARITACA_ENABLED=True, MARITACA_API_KEY="",
            AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        ),
        dict(ollama=False, anthropic=False, groq=False, maritaca=False),
    ),
    (
        "kill_switch_barra_todos_externos_mantem_local",
        dict(
            OLLAMA_ENABLED=True,
            ANTHROPIC_ENABLED=True, ANTHROPIC_API_KEY="sk-ant-fake",
            GROQ_API_KEY="gsk-fake",
            MARITACA_ENABLED=True, MARITACA_API_KEY="mrt-fake",
            AI_EXTERNAL_PROVIDERS_ALLOWED=False,  # kill-switch
        ),
        dict(ollama=True, anthropic=False, groq=False, maritaca=False),
    ),
    (
        "tudo_ligado_e_permitido",
        dict(
            OLLAMA_ENABLED=True,
            ANTHROPIC_ENABLED=True, ANTHROPIC_API_KEY="sk-ant-fake",
            GROQ_API_KEY="gsk-fake",
            MARITACA_ENABLED=True, MARITACA_API_KEY="mrt-fake",
            AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        ),
        dict(ollama=True, anthropic=True, groq=True, maritaca=True),
    ),
]


def _aplicar(monkeypatch, overrides: dict) -> None:
    st = get_settings()
    for k, v in overrides.items():
        monkeypatch.setattr(st, k, v, raising=False)


def _assert_tres_fontes_concordam(esperado: dict) -> None:
    for p in PROVIDERS:
        via_registry = provider_registry.provider_elegivel(p)
        via_gateway = ai_gateway._provider_elegivel(p)
        via_policy = AIProviderPolicy._elegivel(p)
        # As três fontes concordam entre si...
        assert via_gateway == via_policy == via_registry, (
            f"drift de elegibilidade em {p!r}: gateway={via_gateway} "
            f"policy={via_policy} registry={via_registry}"
        )
        # ...e concordam com o comportamento esperado do cenário.
        assert via_registry is esperado[p], (
            f"elegibilidade inesperada em {p!r}: obtido={via_registry} "
            f"esperado={esperado[p]}"
        )


@pytest.mark.parametrize("nome, overrides, esperado", CENARIOS,
                         ids=[c[0] for c in CENARIOS])
def test_tres_fontes_de_elegibilidade_concordam(nome, overrides, esperado, monkeypatch):
    _aplicar(monkeypatch, overrides)
    _assert_tres_fontes_concordam(esperado)


@pytest.mark.parametrize("nome, overrides, esperado", CENARIOS,
                         ids=[c[0] for c in CENARIOS])
def test_concordancia_persiste_apos_instalar_runtime(nome, overrides, esperado, monkeypatch):
    # `instalar()` reatribui os símbolos à fonte única (redundante após a
    # delegação, mas deve continuar consistente e idempotente).
    from app.services.ai.provider_registry_runtime import instalar
    instalar()
    _aplicar(monkeypatch, overrides)
    _assert_tres_fontes_concordam(esperado)


def test_provider_desconhecido_e_inelegivel_nas_tres_fontes():
    p = "provedor_inexistente"
    assert provider_registry.provider_elegivel(p) is False
    assert ai_gateway._provider_elegivel(p) is False
    assert AIProviderPolicy._elegivel(p) is False
