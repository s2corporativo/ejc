"""Cliente da API oficial de Localidades do IBGE.

Usado para canonicalizar município/UF/código IBGE em cadastros e cruzamentos
com bases públicas. Não recebe endereço completo nem persiste dado pessoal.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import Any

import httpx

from app.integrations.feature_flags import require_enabled


IBGE_LOCALIDADES_BASE = "https://servicodados.ibge.gov.br/api/v1/localidades"
_UF_RE = re.compile(r"^[A-Z]{2}$")
_TRANSIENTES = {429, 500, 502, 503, 504}


class IbgeLocalidadesError(RuntimeError):
    pass


def _norm(texto: str) -> str:
    base = unicodedata.normalize("NFKD", (texto or "").strip().casefold())
    return "".join(c for c in base if not unicodedata.combining(c))


def _normalizar_municipio(item: dict[str, Any]) -> dict[str, Any]:
    micror = item.get("microrregiao") or {}
    mesor = micror.get("mesorregiao") or {}
    uf = mesor.get("UF") or {}
    regiao_imediata = item.get("regiao-imediata") or {}
    regiao_intermediaria = regiao_imediata.get("regiao-intermediaria") or {}
    uf2 = regiao_intermediaria.get("UF") or {}
    uf_final = uf2 or uf
    regiao = uf_final.get("regiao") or {}
    return {
        "id": item.get("id"),
        "nome": item.get("nome"),
        "uf_id": uf_final.get("id"),
        "uf_sigla": uf_final.get("sigla"),
        "uf_nome": uf_final.get("nome"),
        "regiao_id": regiao.get("id"),
        "regiao_sigla": regiao.get("sigla"),
        "regiao_nome": regiao.get("nome"),
        "fonte": "IBGE — API de Localidades",
    }


class IbgeLocalidadesClient:
    def __init__(self, timeout_s: float = 15.0) -> None:
        self.timeout = httpx.Timeout(timeout_s)

    async def _get(self, path: str) -> Any:
        require_enabled("ibge", "IBGE Localidades")
        url = f"{IBGE_LOCALIDADES_BASE}/{path.lstrip('/')}"
        ultimo: Exception | None = None
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"Accept": "application/json", "User-Agent": "EJC/1.0 IBGE-localidades"},
            follow_redirects=True,
        ) as client:
            for tentativa in range(2):
                try:
                    resp = await client.get(url)
                    if resp.status_code in _TRANSIENTES:
                        raise httpx.HTTPStatusError(
                            f"HTTP {resp.status_code}", request=resp.request, response=resp
                        )
                    resp.raise_for_status()
                    return resp.json()
                except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                    ultimo = exc
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status is not None and 400 <= status < 500 and status != 429:
                        break
                    if tentativa == 0:
                        await asyncio.sleep(0.4)
        status = getattr(getattr(ultimo, "response", None), "status_code", None)
        raise IbgeLocalidadesError(
            f"IBGE Localidades indisponível{f' (HTTP {status})' if status else ''}"
        ) from ultimo

    async def municipios_por_uf(self, uf: str) -> list[dict[str, Any]]:
        sigla = (uf or "").strip().upper()
        if not _UF_RE.fullmatch(sigla):
            raise ValueError("UF deve conter exatamente duas letras")
        payload = await self._get(f"estados/{sigla}/municipios")
        if not isinstance(payload, list):
            raise IbgeLocalidadesError("IBGE retornou formato inesperado para municípios")
        return [_normalizar_municipio(x) for x in payload if isinstance(x, dict)]

    async def municipio_por_id(self, municipio_id: int | str) -> dict[str, Any]:
        valor = str(municipio_id).strip()
        if not valor.isdigit() or len(valor) > 10:
            raise ValueError("Código IBGE de município inválido")
        payload = await self._get(f"municipios/{valor}")
        if not isinstance(payload, dict):
            raise IbgeLocalidadesError("IBGE retornou formato inesperado para município")
        return _normalizar_municipio(payload)

    async def canonicalizar(self, nome: str, uf: str) -> dict[str, Any] | None:
        alvo = _norm(nome)
        if not alvo:
            raise ValueError("nome do município obrigatório")
        municipios = await self.municipios_por_uf(uf)
        exatos = [m for m in municipios if _norm(str(m.get("nome") or "")) == alvo]
        return exatos[0] if len(exatos) == 1 else None
