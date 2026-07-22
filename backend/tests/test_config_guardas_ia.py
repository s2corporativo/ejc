"""Guardas LGPD de IA no boot (P2 — auditoria Central de IA).

Espelha o estilo de test_estabilizacao_auditoria.py (`_prod_kwargs` + Settings),
mas importa SOMENTE app.core.config — sem tocar routers/app.main — para rodar
isolado (o import de routers puxa SDKs externos opcionais).

Contrato:
  - produção + provider externo elegível + AI_REQUIRE_SANITIZATION_FOR_EXTERNAL
    false → boot FALHA, a menos que AI_ACCEPT_EXTERNAL_WITHOUT_SANITIZATION=true;
  - MARITACA_EXIGIR_SOBERANIA=true + MARITACA_ENABLED=true exige modelos "-br-sp";
  - defaults (flags OFF) preservam o comportamento atual.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings


def _prod_kwargs(**over):
    """Kwargs mínimos que passam TODOS os guardas de produção pré-existentes
    (SECRET_KEY/PII/VAULT/CORS/FRONTEND). Cada teste sobrepõe só o que exercita."""
    base = dict(
        _env_file=None,           # não lê .env do host: teste determinístico
        APP_ENV="production",
        SECRET_KEY="s" * 64,
        PII_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        PII_HASH_KEY="h" * 32,
        VAULT_MASTER_KEYS=Fernet.generate_key().decode(),
        FRONTEND_URL="https://app.exemplo.adv.br",
        CORS_ORIGINS="https://app.exemplo.adv.br",
        # Baseline seguro: sem provider externo elegível por padrão.
        ANTHROPIC_API_KEY="",
        ANTHROPIC_ENABLED=True,
        GROQ_API_KEY="",
        MARITACA_ENABLED=False,
        MARITACA_API_KEY="",
        AI_EXTERNAL_PROVIDERS_ALLOWED=True,
    )
    base.update(over)
    return base


# ── Guarda 1: sanitização obrigatória p/ provider externo ─────────────────────

def test_producao_recusa_externo_sem_sanitizacao():
    """Provider externo elegível (Anthropic c/ chave) + sanitização OFF, sem
    override consciente → boot FALHA."""
    with pytest.raises(ValueError, match="SANITIZATION"):
        Settings(**_prod_kwargs(
            ANTHROPIC_API_KEY="sk-x",
            AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=False,
        ))


def test_producao_recusa_groq_sem_sanitizacao():
    """Basta UM externo elegível (Groq c/ chave) para exigir sanitização."""
    with pytest.raises(ValueError, match="SANITIZATION"):
        Settings(**_prod_kwargs(
            GROQ_API_KEY="gk",
            AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=False,
        ))


def test_producao_externo_sem_sanitizacao_com_override_consciente():
    """Override explícito e auditável libera a exceção (não levanta)."""
    s = Settings(**_prod_kwargs(
        GROQ_API_KEY="gk",
        AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=False,
        AI_ACCEPT_EXTERNAL_WITHOUT_SANITIZATION=True,
    ))
    assert s.AI_ACCEPT_EXTERNAL_WITHOUT_SANITIZATION is True


def test_producao_sanitizacao_off_sem_externo_elegivel_ok():
    """Sem provider externo elegível (kill-switch OFF), sanitização OFF não
    dispara o guarda — nada sai do VPS de qualquer forma."""
    s = Settings(**_prod_kwargs(
        AI_EXTERNAL_PROVIDERS_ALLOWED=False,
        ANTHROPIC_API_KEY="sk-x",   # há chave, mas kill-switch OFF → inelegível
        AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=False,
    ))
    assert s.AI_REQUIRE_SANITIZATION_FOR_EXTERNAL is False


def test_producao_sanitizacao_on_com_externo_ok():
    """Sanitização ON (default) + externo elegível: comportamento normal."""
    s = Settings(**_prod_kwargs(ANTHROPIC_API_KEY="sk-x"))
    assert s.AI_REQUIRE_SANITIZATION_FOR_EXTERNAL is True


def test_desenvolvimento_nao_aplica_guarda_sanitizacao():
    """Fora de produção o guarda não roda (não levanta)."""
    s = Settings(
        _env_file=None, APP_ENV="development",
        ANTHROPIC_API_KEY="sk-x", AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=False,
    )
    assert s.AI_REQUIRE_SANITIZATION_FOR_EXTERNAL is False


# ── Guarda 2: soberania Maritaca (modelos -br-sp) ─────────────────────────────

def test_producao_soberania_maritaca_exige_br_sp():
    """MARITACA_EXIGIR_SOBERANIA=true + modelo não-soberano → boot FALHA."""
    with pytest.raises(ValueError, match="br-sp"):
        Settings(**_prod_kwargs(
            MARITACA_ENABLED=True, MARITACA_API_KEY="mk",
            MARITACA_EXIGIR_SOBERANIA=True,
            MARITACA_MODEL="sabia-4", MARITACA_MODEL_RAPIDO="sabiazinho-4",
        ))


def test_producao_soberania_maritaca_rapido_nao_br_sp_falha():
    """Ambos os modelos precisam ser -br-sp: só o principal não basta."""
    with pytest.raises(ValueError, match="MARITACA_MODEL_RAPIDO"):
        Settings(**_prod_kwargs(
            MARITACA_ENABLED=True, MARITACA_API_KEY="mk",
            MARITACA_EXIGIR_SOBERANIA=True,
            MARITACA_MODEL="sabia-4-br-sp", MARITACA_MODEL_RAPIDO="sabiazinho-4",
        ))


def test_producao_soberania_maritaca_aceita_br_sp():
    """Com as variantes -br-sp em ambos, o modo soberania passa no boot."""
    s = Settings(**_prod_kwargs(
        MARITACA_ENABLED=True, MARITACA_API_KEY="mk",
        MARITACA_EXIGIR_SOBERANIA=True,
        MARITACA_MODEL="sabia-4-br-sp", MARITACA_MODEL_RAPIDO="sabiazinho-4-br-sp",
    ))
    assert s.MARITACA_MODEL.endswith("-br-sp")


def test_producao_soberania_off_nao_valida_modelo():
    """Default (MARITACA_EXIGIR_SOBERANIA=false) não exige -br-sp: inalterado."""
    s = Settings(**_prod_kwargs(
        MARITACA_ENABLED=True, MARITACA_API_KEY="mk", MARITACA_MODEL="sabia-4",
    ))
    assert s.MARITACA_EXIGIR_SOBERANIA is False


def test_producao_soberania_on_mas_maritaca_off_nao_valida():
    """Soberania exigida mas Maritaca desligado: guarda não roda (provider inativo)."""
    s = Settings(**_prod_kwargs(
        MARITACA_ENABLED=False, MARITACA_EXIGIR_SOBERANIA=True,
        MARITACA_MODEL="sabia-4",
    ))
    assert s.MARITACA_EXIGIR_SOBERANIA is True
