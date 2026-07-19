# ── app/services/credential_registry.py ──────────────────────────────────────
# Catálogo ESTÁTICO do Cofre de Credenciais: quais integrações existem e quais
# campos secretos cada uma usa. É a fonte única de verdade para:
#   * a UI de Configurações → Credenciais (PR-5): lista providers/campos;
#   * o import do .env (PR-6): que atributos de Settings viram registros;
#   * validação de escrita no router (PR-3): provider/field fora do catálogo
#     é rejeitado — nada de campo arbitrário virando setattr no Settings.
#
# CONTRATO CENTRAL: `field_key` é o nome EXATO do atributo em
# app.core.config.Settings (validado por introspecção em
# tests/test_vault_fundacao.py). É isso que permite ao overlay (PR-2) aplicar
# a credencial com setattr no singleton get_settings() sem tabela de mapeamento.
#
# `tipo` (domínio do VARCHAR integration_credentials.tipo):
#   api_key | token | login | senha | oauth_client
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CampoCredencial:
    field_key: str      # nome EXATO do atributo em Settings
    tipo: str           # api_key | token | login | senha | oauth_client
    rotulo: str         # rótulo humano exibido na UI
    obrigatorio: bool = True  # False = integração funciona sem este campo


# provider_key → campos. Ordem dos campos = ordem de exibição na UI.
REGISTRY: dict[str, tuple[CampoCredencial, ...]] = {
    "datajud": (
        CampoCredencial("DATAJUD_API_KEY", "api_key", "API Key pública do DataJud (CNJ)"),
    ),
    "groq": (
        CampoCredencial("GROQ_API_KEY", "api_key", "API Key da Groq"),
    ),
    "anthropic": (
        CampoCredencial("ANTHROPIC_API_KEY", "api_key", "API Key da Anthropic (Claude)"),
    ),
    "maritaca": (
        CampoCredencial("MARITACA_API_KEY", "api_key", "API Key da Maritaca (Sabiá)"),
    ),
    "infosimples": (
        CampoCredencial("INFOSIMPLES_TOKEN", "token", "Token da Infosimples"),
    ),
    "smtp": (
        CampoCredencial("SMTP_USER", "login", "Usuário SMTP"),
        CampoCredencial("SMTP_PASSWORD", "senha", "Senha SMTP"),
    ),
    "nfse": (
        CampoCredencial("NFSE_NUVEMFISCAL_CLIENT_ID", "oauth_client",
                        "Client ID OAuth da NuvemFiscal"),
        CampoCredencial("NFSE_NUVEMFISCAL_CLIENT_SECRET", "oauth_client",
                        "Client Secret OAuth da NuvemFiscal"),
    ),
    "transparencia": (
        CampoCredencial("TRANSPARENCIA_API_KEY", "api_key",
                        "API Key do Portal da Transparência"),
    ),
    "langfuse": (
        CampoCredencial("LANGFUSE_PUBLIC_KEY", "api_key", "Public Key do Langfuse"),
        CampoCredencial("LANGFUSE_SECRET_KEY", "api_key", "Secret Key do Langfuse"),
    ),
    "push_vapid": (
        CampoCredencial("VAPID_PUBLIC_KEY", "token", "Chave pública VAPID (Web Push)"),
        CampoCredencial("VAPID_PRIVATE_KEY", "token", "Chave privada VAPID (Web Push)"),
    ),
}

TIPOS_VALIDOS = frozenset({"api_key", "token", "login", "senha", "oauth_client"})


def campos_do_provider(provider_key: str) -> tuple[CampoCredencial, ...]:
    """Campos de um provider, ou tupla vazia se não catalogado."""
    return REGISTRY.get(provider_key, ())


def buscar_campo(provider_key: str, field_key: str) -> CampoCredencial | None:
    """Campo exato do catálogo, ou None — gate de escrita do router (PR-3)."""
    for campo in REGISTRY.get(provider_key, ()):
        if campo.field_key == field_key:
            return campo
    return None


def todos_field_keys() -> list[str]:
    """Todos os field_keys do catálogo (ordem de exibição)."""
    return [c.field_key for campos in REGISTRY.values() for c in campos]
