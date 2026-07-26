"""
Cliente de integração com a BrasilAPI (brasilapi.com.br).

Projeto comunitário (não é API oficial do governo), gratuito, sem
necessidade de chave/autenticação. Útil para validação rápida de CNPJ/CEP
no cadastro de clientes do EJC, como complemento — não substituto — da
fonte oficial quando exigida fundamentação formal (nesse caso, usar o
Conecta gov.br, integração ainda pendente de credenciamento institucional).

Documentação: https://brasilapi.com.br/docs
"""

from __future__ import annotations

from typing import Any

import httpx

BRASILAPI_BASE_URL = "https://brasilapi.com.br/api"


class BrasilApiError(RuntimeError):
    """Erro de integração com a BrasilAPI."""


class BrasilApiClient:
    def __init__(self, timeout_s: float = 10.0) -> None:
        self._timeout = httpx.Timeout(timeout_s)

    async def consultar_cnpj(self, cnpj: str) -> dict[str, Any]:
        cnpj_limpo = "".join(ch for ch in cnpj if ch.isdigit())
        url = f"{BRASILAPI_BASE_URL}/cnpj/v1/{cnpj_limpo}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            raise BrasilApiError(
                f"BrasilAPI (CNPJ) retornou HTTP {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    async def consultar_cep(self, cep: str) -> dict[str, Any]:
        cep_limpo = "".join(ch for ch in cep if ch.isdigit())
        url = f"{BRASILAPI_BASE_URL}/cep/v2/{cep_limpo}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            raise BrasilApiError(
                f"BrasilAPI (CEP) retornou HTTP {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()
