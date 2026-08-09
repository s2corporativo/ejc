"""Cliente CKAN para portais públicos oficiais usados pelo EJC.

O cliente NÃO aceita host arbitrário: as origens são allowlisted para reduzir
risco de SSRF caso algum consumidor futuro exponha a seleção da fonte em rota.
Ele descobre datasets/recursos e devolve metadados; downloads volumosos não são
feitos implicitamente por requisição HTTP do EJC.

Fontes atuais:
- IBAMA Dados Abertos
- Ministério da Justiça (Consumidor.gov.br/Sindec)
- CVM Dados Abertos
- TSE Dados Abertos
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import httpx


CKAN_BASES: dict[str, str] = {
    "ibama": "https://dadosabertos.ibama.gov.br/api/3/action",
    "mj": "https://dados.mj.gov.br/api/3/action",
    "cvm": "https://dados.cvm.gov.br/api/3/action",
    "tse": "https://dadosabertos.tse.jus.br/api/3/action",
}

_UA = "EJC/1.0 (+https://depaulateixeira.adv.br; public-data-client)"
_TRANSIENTES = {429, 500, 502, 503, 504}


class CkanPublicError(RuntimeError):
    """Falha segura de integração com um portal CKAN oficial."""


@dataclass(frozen=True)
class CkanResource:
    source: str
    dataset_id: str
    dataset_title: str
    resource_id: str
    name: str
    format: str
    url: str
    last_modified: str | None = None
    created: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CkanPublicClient:
    def __init__(self, source: str, timeout_s: float = 20.0) -> None:
        if source not in CKAN_BASES:
            raise ValueError(f"Fonte CKAN não permitida: {source!r}")
        self.source = source
        self.base_url = CKAN_BASES[source]
        self.timeout = httpx.Timeout(timeout_s)

    async def _get(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{action}"
        ultimo: Exception | None = None
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"Accept": "application/json", "User-Agent": _UA},
            follow_redirects=True,
        ) as client:
            for tentativa in range(2):
                try:
                    resp = await client.get(url, params=params)
                    if resp.status_code in _TRANSIENTES:
                        raise httpx.HTTPStatusError(
                            f"HTTP {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    resp.raise_for_status()
                    payload = resp.json()
                    if not isinstance(payload, dict) or payload.get("success") is not True:
                        raise CkanPublicError(
                            f"{self.source}: resposta CKAN inválida em {action}"
                        )
                    result = payload.get("result")
                    if not isinstance(result, dict):
                        raise CkanPublicError(
                            f"{self.source}: result CKAN ausente em {action}"
                        )
                    return result
                except CkanPublicError:
                    raise
                except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                    ultimo = exc
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status is not None and 400 <= status < 500 and status != 429:
                        break
                    if tentativa == 0:
                        await asyncio.sleep(0.5)
        status = getattr(getattr(ultimo, "response", None), "status_code", None)
        sufixo = f" (HTTP {status})" if status else ""
        raise CkanPublicError(f"{self.source}: serviço CKAN indisponível{sufixo}") from ultimo

    async def package_search(self, query: str, *, rows: int = 10) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            raise ValueError("query CKAN obrigatória")
        rows = max(1, min(int(rows), 20))
        return await self._get("package_search", {"q": query, "rows": rows})

    async def package_show(self, dataset_id: str) -> dict[str, Any]:
        dataset_id = (dataset_id or "").strip()
        if not dataset_id:
            raise ValueError("dataset_id obrigatório")
        return await self._get("package_show", {"id": dataset_id})

    @staticmethod
    def _normalizar_formatos(formatos: Iterable[str] | None) -> set[str]:
        return {str(x).strip().upper() for x in (formatos or []) if str(x).strip()}

    async def recursos_por_busca(
        self,
        query: str,
        *,
        formatos: Iterable[str] | None = None,
        rows: int = 5,
        limit: int = 20,
    ) -> list[CkanResource]:
        """Descobre recursos de datasets sem baixar os arquivos.

        `limit` limita o retorno mesmo quando o portal possui dezenas de recursos.
        A ordenação prioriza last_modified/created mais recentes.
        """
        resultado = await self.package_search(query, rows=rows)
        datasets = resultado.get("results") or []
        permitidos = self._normalizar_formatos(formatos)
        recursos: list[CkanResource] = []
        for ds in datasets:
            if not isinstance(ds, dict):
                continue
            ds_id = str(ds.get("id") or ds.get("name") or "").strip()
            if not ds_id:
                continue
            titulo = str(ds.get("title") or ds.get("name") or ds_id).strip()
            for rec in ds.get("resources") or []:
                if not isinstance(rec, dict):
                    continue
                formato = str(rec.get("format") or "").strip().upper()
                if permitidos and formato not in permitidos:
                    continue
                url = str(rec.get("url") or "").strip()
                rec_id = str(rec.get("id") or "").strip()
                if not url or not rec_id or not url.startswith("https://"):
                    continue
                recursos.append(CkanResource(
                    source=self.source,
                    dataset_id=ds_id,
                    dataset_title=titulo,
                    resource_id=rec_id,
                    name=str(rec.get("name") or rec.get("description") or rec_id).strip(),
                    format=formato,
                    url=url,
                    last_modified=(str(rec.get("last_modified")) if rec.get("last_modified") else None),
                    created=(str(rec.get("created")) if rec.get("created") else None),
                ))
        recursos.sort(
            key=lambda r: (r.last_modified or r.created or "", r.name),
            reverse=True,
        )
        return recursos[: max(1, min(int(limit), 100))]

    async def recurso_mais_recente(
        self,
        query: str,
        *,
        formatos: Iterable[str] | None = None,
    ) -> CkanResource | None:
        recursos = await self.recursos_por_busca(
            query, formatos=formatos, rows=5, limit=100
        )
        return recursos[0] if recursos else None
