"""AI_PROFILE deriva as flags de provedor (S3 da análise E2E 03/09/2026)."""
from __future__ import annotations

import pytest

from app.core.config import Settings

_BASE = dict(
    _env_file=None,
    APP_ENV="development",
    SECRET_KEY="teste-ai-profile-0123456789abcdef",
    ANTHROPIC_API_KEY="sk-ant-teste",
    GROQ_API_KEY="gsk-teste",
)


def test_vazio_mantem_flags_manuais():
    s = Settings(**_BASE, AI_PROFILE="", OLLAMA_ENABLED=True, GROQ_ENABLED=False)
    assert s.OLLAMA_ENABLED is True
    assert s.GROQ_ENABLED is False
    assert s.AI_ENABLED is True


def test_desligado_e_kill_switch():
    s = Settings(**_BASE, AI_PROFILE="desligado")
    assert s.AI_ENABLED is False


def test_local_so_ollama():
    s = Settings(**_BASE, AI_PROFILE="local")
    assert s.AI_EXTERNAL_PROVIDERS_ALLOWED is False
    assert s.OLLAMA_ENABLED is True
    assert (s.ANTHROPIC_ENABLED, s.GROQ_ENABLED, s.MARITACA_ENABLED) == (False, False, False)
    assert s.AI_PROVIDER_PRIORITY == "ollama"


def test_externo_sem_ollama_e_maritaca_opt_in():
    s = Settings(**_BASE, AI_PROFILE="externo")
    assert s.AI_EXTERNAL_PROVIDERS_ALLOWED is True
    assert s.OLLAMA_ENABLED is False
    assert s.AI_PROVIDER_PRIORITY == "anthropic,groq"
    s2 = Settings(**_BASE, AI_PROFILE="Externo", MARITACA_ENABLED=True)
    assert s2.AI_PROVIDER_PRIORITY == "anthropic,maritaca,groq"
    assert s2.AI_PROFILE == "externo"  # canonizado


def test_hibrido_tudo_com_ollama_por_ultimo():
    s = Settings(**_BASE, AI_PROFILE="hibrido")
    assert s.OLLAMA_ENABLED is True and s.ANTHROPIC_ENABLED is True
    assert s.AI_PROVIDER_PRIORITY == "anthropic,maritaca,groq,ollama"


def test_perfil_invalido_falha_no_boot():
    with pytest.raises(ValueError, match="AI_PROFILE inválido"):
        Settings(**_BASE, AI_PROFILE="nuvem")


def test_perfil_alimenta_a_fonte_unica_de_elegibilidade():
    from app.services.ai.provider_registry import provider_elegivel_com

    local = Settings(**_BASE, AI_PROFILE="local")
    assert provider_elegivel_com("anthropic", local) is False
    assert provider_elegivel_com("ollama", local) is True
    externo = Settings(**_BASE, AI_PROFILE="externo")
    assert provider_elegivel_com("anthropic", externo) is True
    assert provider_elegivel_com("ollama", externo) is False
