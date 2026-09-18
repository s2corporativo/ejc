"""Transporte HTTP exclusivo do DJEN/Comunica CNJ.

Mantém o endpoint oficial e, opcionalmente, usa um proxy HTTP CONNECT privado
para fornecer egress brasileiro. A configuração vem exclusivamente da env
DJEN_HTTP_PROXY_URL, é tratada como SecretStr local e nunca é logada.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

DJEN_COMUNICA_BASE_URL = "https://comunicaapi.pje.jus.br/api/v1"
DJEN_COMUNICACAO_URL = f"{DJEN_COMUNICA_BASE_URL}/comunicacao"
# Valor conservador e compatível com o limite observado em produção do Comunica.
DJEN_ITENS_POR_PAGINA = 50


def obter_proxy_djen() -> str | None:
    bruto = (os.getenv("DJEN_HTTP_PROXY_URL") or "").strip()
    if not bruto:
        return None
    segredo = SecretStr(bruto)
    valor = segredo.get_secret_value().strip()
    parsed = urlsplit(valor)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("DJEN_HTTP_PROXY_URL inválida: use proxy HTTP(S) privado")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RuntimeError("DJEN_HTTP_PROXY_URL inválida: path/query/fragment não permitidos")
    return valor


def criar_cliente_djen(*, timeout: float | httpx.Timeout) -> httpx.AsyncClient:
    """Cria cliente isolado do DJEN; proxy global do host nunca é herdado."""
    proxy = obter_proxy_djen()
    kwargs: dict[str, object] = {"timeout": timeout, "trust_env": False}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.AsyncClient(**kwargs)
