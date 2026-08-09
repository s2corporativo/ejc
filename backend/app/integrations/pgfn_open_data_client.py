"""Descoberta dos arquivos oficiais de Dados Abertos da PGFN.

A PGFN publica trimestralmente a base completa da Dívida Ativa em arquivos
abertos, segmentados por sistema/UF. Este cliente NÃO baixa a base inteira numa
requisição do usuário: apenas descobre links oficiais para processamento em job
controlado/offline.
"""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx


PGFN_DADOS_ABERTOS = (
    "https://www.gov.br/pgfn/pt-br/assuntos/divida-ativa-da-uniao/"
    "transparencia-fiscal-1/dados-abertos"
)
_TRANSIENTES = {429, 500, 502, 503, 504}
_ALLOWED_SUFFIXES = (".csv", ".zip", ".7z", ".gz")


class PgfnOpenDataError(RuntimeError):
    pass


class _LinksParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._texto: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "a":
            return
        self._href = next((v for k, v in attrs if k.lower() == "href"), None)
        self._texto = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._texto.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, " ".join(self._texto).strip()))
            self._href = None
            self._texto = []


def _link_oficial(href: str) -> bool:
    p = urlparse(href)
    host = (p.hostname or "").lower()
    if not host:
        return False
    return host == "gov.br" or host.endswith(".gov.br") or host.endswith(".pgfn.gov.br")


def _parece_recurso(url: str, texto: str) -> bool:
    alvo = f"{url} {texto}".lower()
    return (
        any(ext in alvo for ext in _ALLOWED_SUFFIXES)
        or "dadosabertos" in alvo
        or "dados-abertos" in alvo
        or "download" in alvo
    )


class PgfnOpenDataClient:
    def __init__(self, timeout_s: float = 25.0) -> None:
        self.timeout = httpx.Timeout(timeout_s)

    async def listar_recursos(self, *, ano: int | None = None) -> list[dict[str, str]]:
        if ano is not None and not (2019 <= int(ano) <= 2100):
            raise ValueError("ano fora do intervalo esperado")
        ultimo: Exception | None = None
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"Accept": "text/html", "User-Agent": "EJC/1.0 PGFN-open-data"},
            follow_redirects=True,
        ) as client:
            for tentativa in range(2):
                try:
                    resp = await client.get(PGFN_DADOS_ABERTOS)
                    if resp.status_code in _TRANSIENTES:
                        raise httpx.HTTPStatusError(
                            f"HTTP {resp.status_code}", request=resp.request, response=resp
                        )
                    resp.raise_for_status()
                    parser = _LinksParser()
                    parser.feed(resp.text)
                    saida: list[dict[str, str]] = []
                    vistos: set[str] = set()
                    for href, texto in parser.links:
                        url = urljoin(str(resp.url), href)
                        if url in vistos or not _link_oficial(url):
                            continue
                        if not _parece_recurso(url, texto):
                            continue
                        if ano is not None and str(ano) not in f"{url} {texto}":
                            continue
                        vistos.add(url)
                        saida.append({
                            "url": url,
                            "rotulo": texto or url.rsplit("/", 1)[-1],
                            "fonte": "PGFN — Dados Abertos da Dívida Ativa",
                        })
                    return saida
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    ultimo = exc
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status is not None and 400 <= status < 500 and status != 429:
                        break
                    if tentativa == 0:
                        await asyncio.sleep(0.5)
        status = getattr(getattr(ultimo, "response", None), "status_code", None)
        raise PgfnOpenDataError(
            f"PGFN Dados Abertos indisponível{f' (HTTP {status})' if status else ''}"
        ) from ultimo
