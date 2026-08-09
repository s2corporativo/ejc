"""Cliente REST dos Dados Abertos do TCU para acórdãos.

O cliente limita paginação e normaliza somente campos públicos necessários para
pesquisa/RAG. Não executa download do PDF/inteiro teor automaticamente.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.integrations.feature_flags import require_enabled


TCU_ACORDAOS_URL = "https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos"
_TRANSIENTES = {429, 500, 502, 503, 504}


class TcuPublicError(RuntimeError):
    pass


def _normalizar_acordao(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "chave": item.get("key") or item.get("chave"),
        "tipo": item.get("tipo"),
        "ano": item.get("anoAcordao") or item.get("ano"),
        "numero": item.get("numeroAcordao") or item.get("numero"),
        "titulo": item.get("titulo"),
        "colegiado": item.get("colegiado"),
        "data_sessao": item.get("dataSessao"),
        "relator": item.get("relator"),
        "situacao": item.get("situacao"),
        "sumario": item.get("sumario"),
        "url": item.get("urlAcordao") or item.get("urlArquivo"),
        "url_pdf": item.get("urlArquivoPDF"),
        "fonte": "TCU — Dados Abertos",
    }


class TcuPublicClient:
    def __init__(self, timeout_s: float = 25.0) -> None:
        self.timeout = httpx.Timeout(timeout_s)

    async def listar_acordaos(
        self, *, inicio: int = 0, quantidade: int = 50
    ) -> list[dict[str, Any]]:
        require_enabled("tcu", "TCU Dados Abertos")
        inicio = max(0, int(inicio))
        quantidade = max(1, min(int(quantidade), 100))
        ultimo: Exception | None = None
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "EJC/1.0 (+https://depaulateixeira.adv.br; tcu-open-data)",
            },
            follow_redirects=True,
        ) as client:
            for tentativa in range(2):
                try:
                    resp = await client.get(
                        TCU_ACORDAOS_URL,
                        params={"inicio": inicio, "quantidade": quantidade},
                    )
                    if resp.status_code in _TRANSIENTES:
                        raise httpx.HTTPStatusError(
                            f"HTTP {resp.status_code}", request=resp.request, response=resp
                        )
                    resp.raise_for_status()
                    payload = resp.json()
                    if isinstance(payload, list):
                        itens = payload
                    elif isinstance(payload, dict):
                        itens = (
                            payload.get("items")
                            or payload.get("result")
                            or payload.get("acordaos")
                            or payload.get("dados")
                            or []
                        )
                    else:
                        itens = []
                    if not isinstance(itens, list):
                        raise TcuPublicError("TCU retornou formato inesperado")
                    return [
                        _normalizar_acordao(x) for x in itens if isinstance(x, dict)
                    ]
                except TcuPublicError:
                    raise
                except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                    ultimo = exc
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status is not None and 400 <= status < 500 and status != 429:
                        break
                    if tentativa == 0:
                        await asyncio.sleep(0.5)
        status = getattr(getattr(ultimo, "response", None), "status_code", None)
        raise TcuPublicError(
            f"TCU Dados Abertos indisponível{f' (HTTP {status})' if status else ''}"
        ) from ultimo
