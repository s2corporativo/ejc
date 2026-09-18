"""Transporte HTTP exclusivo do DJEN/Comunica CNJ.

Mantém o endpoint oficial e suporta, em ordem de precedência:
1) relay HTTPS assinado (egress brasileiro controlado);
2) proxy HTTP CONNECT privado;
3) conexão direta.

Nenhuma credencial é logada. O relay recebe apenas assinatura Ed25519 de curta
validade e só encaminha parâmetros DJEN permitidos.
"""
from __future__ import annotations

import base64
import os
import time
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pydantic import SecretStr

DJEN_COMUNICA_BASE_URL = "https://comunicaapi.pje.jus.br/api/v1"
DJEN_COMUNICACAO_URL = f"{DJEN_COMUNICA_BASE_URL}/comunicacao"
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


def obter_relay_djen() -> str | None:
    bruto = (os.getenv("DJEN_RELAY_URL") or "").strip()
    if not bruto:
        return None
    parsed = urlsplit(bruto)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("DJEN_RELAY_URL inválida: relay deve usar HTTPS")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise RuntimeError("DJEN_RELAY_URL inválida: credenciais/query/fragment não permitidos")
    return bruto.rstrip("/")


def _carregar_chave_privada_relay() -> Ed25519PrivateKey:
    bruto = (os.getenv("DJEN_RELAY_PRIVATE_KEY_B64") or "").strip()
    if not bruto:
        raise RuntimeError("DJEN_RELAY_PRIVATE_KEY_B64 ausente")
    segredo = SecretStr(bruto)
    try:
        pem = base64.b64decode(segredo.get_secret_value(), validate=True)
        chave = load_pem_private_key(pem, password=None)
    except Exception as exc:
        raise RuntimeError("DJEN_RELAY_PRIVATE_KEY_B64 inválida") from exc
    if not isinstance(chave, Ed25519PrivateKey):
        raise RuntimeError("DJEN_RELAY_PRIVATE_KEY_B64 deve conter chave Ed25519")
    return chave


def _query_canonica(params: dict) -> str:
    pares = sorted(
        (str(chave), str(valor))
        for chave, valor in params.items()
        if valor is not None
    )
    return urlencode(pares)


def preparar_requisicao_djen(
    params: dict,
) -> tuple[str, dict[str, str], str | None]:
    """Retorna (url, headers, proxy) sem executar rede.

    Em modo relay, assina timestamp + query canônica com Ed25519. Em modo
    proxy/direto, mantém o endpoint oficial sem headers adicionais.
    """
    relay = obter_relay_djen()
    if relay:
        timestamp = str(int(time.time()))
        canonica = _query_canonica(params)
        payload = f"{timestamp}\n{canonica}".encode("utf-8")
        assinatura = _carregar_chave_privada_relay().sign(payload)
        assinatura_b64 = base64.urlsafe_b64encode(assinatura).decode().rstrip("=")
        return (
            relay,
            {
                "x-ejc-timestamp": timestamp,
                "x-ejc-signature": assinatura_b64,
            },
            None,
        )
    return DJEN_COMUNICACAO_URL, {}, obter_proxy_djen()


def criar_cliente_djen(*, timeout: float | httpx.Timeout) -> httpx.AsyncClient:
    """Cria cliente isolado do DJEN; proxy global do host nunca é herdado."""
    proxy = None if obter_relay_djen() else obter_proxy_djen()
    kwargs: dict[str, object] = {"timeout": timeout, "trust_env": False}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.AsyncClient(**kwargs)
