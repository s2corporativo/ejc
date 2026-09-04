"""Cliente da API pública do projeto Querido Diário (Open Knowledge Brasil).

Importante: Querido Diário é um agregador cívico, não a fonte oficial que torna
o ato juridicamente autêntico. O EJC deve sempre preservar o link/arquivo de
origem para conferência humana e jamais tratar o excerto como prova autossuficiente.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any

import httpx

from app.integrations.feature_flags import require_enabled


# Host ATUAL da API. O antigo (`api.queridodiario.ok.org.br`) parou de terminar
# TLS — o handshake falha antes de qualquer HTTP, então a integração inteira
# respondia `QueridoDiarioError` 100% do tempo. Verificado ao vivo em
# 04/09/2026: os dois nomes resolvem para os MESMOS IPs Cloudflare e só o SNI
# muda; `queridodiario.ok.org.br/api/gazettes` redireciona (302) para o host
# abaixo, que responde 200 com o mesmo contrato (`territory_ids`, `querystring`,
# `excerpt_size`, `number_of_excerpts`, `size`, `published_since/until`).
QUERIDO_DIARIO_BASE = "https://api.queridodiario.org.br"
_IBGE_RE = re.compile(r"^\d{7}$")
_TRANSIENTES = {429, 500, 502, 503, 504}


class QueridoDiarioError(RuntimeError):
    pass


class QueridoDiarioClient:
    # 45 s (era 20 s): o host novo foi medido em 7,8 s para `/gazettes` e 23,1 s
    # para `/cities` em 04/09/2026 — com 20 s, parte das chamadas estourava por
    # timeout e virava "indisponível" sem a fonte estar fora do ar.
    def __init__(self, timeout_s: float = 45.0) -> None:
        self.timeout = httpx.Timeout(timeout_s)

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        require_enabled("querido_diario", "Querido Diário")
        ultimo: Exception | None = None
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"Accept": "application/json", "User-Agent": "EJC/1.0 QueridoDiario"},
            follow_redirects=True,
        ) as client:
            for tentativa in range(2):
                try:
                    resp = await client.get(f"{QUERIDO_DIARIO_BASE}/{path.lstrip('/')}", params=params)
                    if resp.status_code in _TRANSIENTES:
                        raise httpx.HTTPStatusError(
                            f"HTTP {resp.status_code}", request=resp.request, response=resp
                        )
                    resp.raise_for_status()
                    try:
                        payload = resp.json()
                    except ValueError as exc:
                        raise QueridoDiarioError("Querido Diário retornou JSON inválido") from exc
                    if not isinstance(payload, dict):
                        raise QueridoDiarioError("Querido Diário retornou formato inesperado")
                    return payload
                except QueridoDiarioError:
                    raise
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    ultimo = exc
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status is not None and 400 <= status < 500 and status != 429:
                        break
                    if tentativa == 0:
                        await asyncio.sleep(0.5)
        status = getattr(getattr(ultimo, "response", None), "status_code", None)
        raise QueridoDiarioError(
            f"Querido Diário indisponível{f' (HTTP {status})' if status else ''}"
        ) from ultimo

    async def buscar(
        self,
        *,
        codigo_ibge: str,
        termo: str,
        data_inicio: date | None = None,
        data_fim: date | None = None,
        tamanho: int = 10,
        excerto: int = 500,
    ) -> dict[str, Any]:
        territorio = str(codigo_ibge or "").strip()
        if not _IBGE_RE.fullmatch(territorio):
            raise ValueError("codigo_ibge deve conter 7 dígitos")
        termo = (termo or "").strip()
        if not termo or len(termo) > 300:
            raise ValueError("termo obrigatório (máximo 300 caracteres)")
        tamanho = max(1, min(int(tamanho), 50))
        excerto = max(100, min(int(excerto), 2000))
        if data_inicio and data_fim and data_inicio > data_fim:
            raise ValueError("data_inicio não pode ser posterior a data_fim")

        params: dict[str, Any] = {
            "territory_ids": territorio,
            "querystring": termo,
            "excerpt_size": excerto,
            "number_of_excerpts": 2,
            "size": tamanho,
        }
        if data_inicio:
            params["published_since"] = data_inicio.isoformat()
        if data_fim:
            params["published_until"] = data_fim.isoformat()

        payload = await self._get_json("gazettes", params)
        return {
            **payload,
            "proveniencia_ejc": {
                "fonte": "Querido Diário — Open Knowledge Brasil",
                "natureza": "agregador_secundario",
                "conferencia_original_obrigatoria": True,
            },
        }

    async def cidade(self, codigo_ibge: str) -> dict[str, Any]:
        territorio = str(codigo_ibge or "").strip()
        if not _IBGE_RE.fullmatch(territorio):
            raise ValueError("codigo_ibge deve conter 7 dígitos")
        return await self._get_json(f"cities/{territorio}")
