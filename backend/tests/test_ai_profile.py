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
    assert s.AI_PROVIDER_PRIORITY == "groq,maritaca,anthropic"
    s2 = Settings(**_BASE, AI_PROFILE="Externo", MARITACA_ENABLED=True)
    assert s2.AI_PROVIDER_PRIORITY == "groq,maritaca,anthropic"
    assert s2.AI_PROFILE == "externo"  # canonizado


def test_hibrido_tudo_com_ollama_por_ultimo():
    s = Settings(**_BASE, AI_PROFILE="hibrido")
    assert s.OLLAMA_ENABLED is True and s.ANTHROPIC_ENABLED is True
    assert s.AI_PROVIDER_PRIORITY == "groq,maritaca,ollama,anthropic"


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


# ── Precedência: flag explícita vence o perfil (revisão de segurança, P2-1) ───
# Sem isto, AI_PROFILE=externo no compose desfazia em silêncio o kill-switch
# que o operador aplicou à mão durante um incidente.
def test_flag_explicita_do_operador_vence_o_perfil():
    s = Settings(**_BASE, AI_PROFILE="hibrido", AI_EXTERNAL_PROVIDERS_ALLOWED=False)
    assert s.AI_EXTERNAL_PROVIDERS_ALLOWED is False, (
        "kill-switch explícito não pode ser revertido pelo perfil"
    )
    s2 = Settings(**_BASE, AI_PROFILE="externo", ANTHROPIC_ENABLED=False, GROQ_ENABLED=False)
    assert (s2.ANTHROPIC_ENABLED, s2.GROQ_ENABLED) == (False, False)
    # O que o operador NÃO definiu continua vindo do perfil.
    assert s2.OLLAMA_ENABLED is False


def test_perfil_local_nao_religa_ollama_se_operador_desligou():
    s = Settings(**_BASE, AI_PROFILE="local", OLLAMA_ENABLED=False)
    assert s.OLLAMA_ENABLED is False
    assert s.AI_EXTERNAL_PROVIDERS_ALLOWED is False  # derivado, não explícito


# ── Precedência assimétrica: derivação RESTRITIVA vence o explícito ──────────
# Achado da revisão automatizada do PR (03/09/2026): com a regra "explícito
# sempre vence", `AI_PROFILE=desligado` não desligava nada quando havia um
# `AI_ENABLED=true` no ambiente — o perfil que existe para PARAR a IA era o
# único que podia ser anulado por engano de configuração.
def test_desligado_vence_ai_enabled_explicito():
    s = Settings(**_BASE, AI_PROFILE="desligado", AI_ENABLED=True)
    assert s.AI_ENABLED is False, "AI_PROFILE=desligado é kill-switch: sempre prevalece"
    # Sem flag explícita o resultado é o mesmo (não há regressão do caso base).
    assert Settings(**_BASE, AI_PROFILE="desligado").AI_ENABLED is False


def test_local_desliga_provedor_externo_mesmo_se_explicitamente_ligado():
    s = Settings(**_BASE, AI_PROFILE="local",
                 ANTHROPIC_ENABLED=True, GROQ_ENABLED=True,
                 AI_EXTERNAL_PROVIDERS_ALLOWED=True)
    assert s.AI_EXTERNAL_PROVIDERS_ALLOWED is False
    assert (s.ANTHROPIC_ENABLED, s.GROQ_ENABLED) == (False, False)
    from app.services.ai.provider_registry import provider_elegivel_com
    assert provider_elegivel_com("anthropic", s) is False


def test_derivacao_permissiva_continua_cedendo_ao_explicito():
    # A assimetria não pode virar "o perfil sempre vence": ligar provedor
    # externo contra a vontade explícita do operador é o defeito original.
    s = Settings(**_BASE, AI_PROFILE="externo", AI_EXTERNAL_PROVIDERS_ALLOWED=False)
    assert s.AI_EXTERNAL_PROVIDERS_ALLOWED is False
    # E desligar a IA à mão continua valendo sob qualquer perfil permissivo.
    s2 = Settings(**_BASE, AI_PROFILE="hibrido", AI_ENABLED=False)
    assert s2.AI_ENABLED is False
