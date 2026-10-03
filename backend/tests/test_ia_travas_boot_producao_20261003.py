"""Regressão — travas de boot de produção do núcleo de IA (auditoria 03/10/2026).

NIA-03  produção recusa AI_REQUIRE_HITL=false no boot.
NIA-04  produção recusa EMBEDDINGS_API_URL fora da rede interna com provider http.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings, _host_interno


def _prod_kwargs(**over):
    """Mesmo baseline de tests/test_config_guardas_ia.py: passa todos os
    guardas de produção pré-existentes; cada teste sobrepõe o que exercita."""
    base = dict(
        _env_file=None,
        APP_ENV="production",
        SECRET_KEY="s" * 64,
        PII_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        PII_HASH_KEY="h" * 32,
        VAULT_MASTER_KEYS=Fernet.generate_key().decode(),
        FRONTEND_URL="https://app.exemplo.adv.br",
        CORS_ORIGINS="https://app.exemplo.adv.br",
        ANTHROPIC_API_KEY="",
        GROQ_API_KEY="",
        MARITACA_ENABLED=False,
        MARITACA_API_KEY="",
    )
    base.update(over)
    return base


# ── NIA-03 ────────────────────────────────────────────────────────────────────

def test_producao_recusa_hitl_desligado():
    with pytest.raises(ValueError, match="AI_REQUIRE_HITL"):
        Settings(**_prod_kwargs(AI_REQUIRE_HITL=False))


def test_producao_aceita_hitl_ligado_e_dev_aceita_desligado():
    assert Settings(**_prod_kwargs()).AI_REQUIRE_HITL is True
    assert Settings(_env_file=None, APP_ENV="development",
                    AI_REQUIRE_HITL=False).AI_REQUIRE_HITL is False


# ── NIA-04 ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://embeddings:8010/embed",          # serviço do compose (default)
    "http://localhost:8010/embed",
    "http://127.0.0.1:8010/embed",
    "http://10.0.0.5:8010/embed",
    "http://192.168.1.20/embed",
    "http://embeddings.internal:8010/embed",
    "http://emb.ejc.svc.cluster.local/embed",
])
def test_host_interno_reconhecido(url):
    assert _host_interno(url) is True


@pytest.mark.parametrize("url", [
    "https://api.embeddings-exemplo.com/v1/embed",
    "http://8.8.8.8/embed",
    "",
    "nao-e-url",
    # Revisão do security-auditor: nomes enganosos e faixas "private" que não
    # são rede local.
    "http://embeddings@evil.com/embed",       # userinfo enganoso → host evil.com
    "http://localhost.evil.com/embed",
    "http://embeddings.evil.com/embed",
    "http://0.0.0.0:8010/embed",
    "http://[::]:8010/embed",
    "http://192.0.2.10/embed",
    "http://[2001:db8::1]/embed",
])
def test_host_externo_ou_ilegivel_nao_e_interno(url):
    assert _host_interno(url) is False


def test_producao_recusa_embeddings_http_externo():
    with pytest.raises(ValueError, match="EMBEDDINGS_API_URL"):
        Settings(**_prod_kwargs(
            EMBEDDINGS_PROVIDER="http",
            EMBEDDINGS_API_URL="https://api.embeddings-exemplo.com/v1/embed",
        ))


def test_producao_aceita_embeddings_http_interno_local_ou_excecao_explicita():
    Settings(**_prod_kwargs(EMBEDDINGS_PROVIDER="http"))  # default interno
    Settings(**_prod_kwargs(
        EMBEDDINGS_PROVIDER="local",
        EMBEDDINGS_API_URL="https://api.embeddings-exemplo.com/v1/embed",
    ))
    Settings(**_prod_kwargs(
        EMBEDDINGS_PROVIDER="http",
        EMBEDDINGS_API_URL="https://api.embeddings-exemplo.com/v1/embed",
        EMBEDDINGS_HTTP_EXTERNO_AUTORIZADO=True,
    ))


def test_decisao_bate_com_o_host_que_o_httpx_usa():
    """`evil.com\\@embeddings` parece bypass, mas o host efetivo (urlsplit e
    httpx, o cliente de embedding_service) é `embeddings`: a requisição vai ao
    serviço interno, e `evil.com` vira userinfo."""
    import httpx

    url = "http://evil.com\\@embeddings:8010/embed"
    assert httpx.URL(url).host == "embeddings"
    assert _host_interno(url) is True
