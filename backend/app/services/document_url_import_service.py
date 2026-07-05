# ── app/services/document_url_import_service.py ───────────────────────────────
"""Importação jurídica segura por URL.

Permite transformar páginas públicas em texto/dossiê jurídico para revisão
humana, sem scraping cego e sem executar JavaScript remoto.

Segurança aplicada:
- somente http/https;
- bloqueio de localhost, IP privado, loopback, link-local, multicast, reserved;
- resolução DNS antes de cada request e antes de redirecionamentos;
- redirects manuais com revalidação;
- timeout curto;
- limite máximo de bytes;
- extração HTML simples, sem script/style/noscript.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from pydantic import BaseModel, Field

from app.services.document_intake_service import montar_dossie_documental


MAX_URL_BYTES = 2_000_000
MAX_URL_TEXT_CHARS = 200_000
MAX_REDIRECTS = 3
USER_AGENT = "EJC-DocumentImporter/1.0 (+https://depaulateixeira.adv.br)"


class URLImportError(RuntimeError):
    """Erro esperado de importação por URL."""


class URLImportResult(BaseModel):
    url_original: str
    url_final: str
    status_code: int
    content_type: str | None = None
    titulo: str | None = None
    descricao: str | None = None
    texto: str
    dossie: str
    bloqueado: bool = False
    aviso: str | None = None
    metadados: dict = Field(default_factory=dict)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_stack: list[str] = []
        self._title_on = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.meta_description: str | None = None
        self.canonical: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self._skip_stack.append(tag)
        if tag == "title":
            self._title_on = True
        if tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if name in {"description", "og:description"} and attrs_dict.get("content"):
                self.meta_description = attrs_dict["content"].strip()
        if tag == "link" and attrs_dict.get("rel", "").lower() == "canonical":
            href = attrs_dict.get("href")
            if href:
                self.canonical = href.strip()
        if tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section", "article"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._title_on = False
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()
        if tag in {"p", "li", "tr", "h1", "h2", "h3", "h4", "section", "article"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not data or self._skip_stack:
            return
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        if self._title_on:
            self.title_parts.append(cleaned)
        self.text_parts.append(cleaned + " ")


def _limpar_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise URLImportError("URL vazia.")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise URLImportError("Apenas URLs http/https são permitidas.")
    if not parsed.hostname:
        raise URLImportError("URL sem hostname válido.")
    if parsed.username or parsed.password:
        raise URLImportError("URL com credenciais não é permitida.")
    # Remove fragmento para evitar duplicidade irrelevante.
    return urlunparse(parsed._replace(fragment=""))


def _ip_permitido(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _resolver_ips(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise URLImportError(f"Não foi possível resolver o domínio: {hostname}") from exc
    ips = sorted({info[4][0] for info in infos})
    if not ips:
        raise URLImportError("Domínio sem IP resolvido.")
    return ips


def validar_url_importavel(url: str) -> str:
    """Valida URL contra SSRF e retorna URL normalizada."""
    url = _limpar_url(url)
    parsed = urlparse(url)
    host = parsed.hostname or ""
    host_lower = host.lower().strip(".")
    if host_lower in {"localhost", "localhost.localdomain"} or host_lower.endswith(".local"):
        raise URLImportError("Host local não é permitido.")
    for ip in _resolver_ips(host_lower):
        if not _ip_permitido(ip):
            raise URLImportError("URL aponta para IP interno ou não permitido.")
    return url


def extrair_html_simples(html: str, base_url: str) -> tuple[str | None, str | None, str | None, str]:
    parser = _HTMLTextExtractor()
    parser.feed(html[:MAX_URL_TEXT_CHARS * 4])
    titulo = re.sub(r"\s+", " ", " ".join(parser.title_parts)).strip() or None
    descricao = parser.meta_description
    canonical = urljoin(base_url, parser.canonical) if parser.canonical else None
    bruto = "".join(parser.text_parts)
    linhas = []
    for linha in bruto.splitlines():
        cleaned = re.sub(r"\s+", " ", linha).strip()
        if len(cleaned) >= 3:
            linhas.append(cleaned)
    texto = "\n".join(linhas)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()[:MAX_URL_TEXT_CHARS]
    return titulo, descricao, canonical, texto


async def _fetch_bytes_seguro(url: str) -> tuple[str, int, str | None, bytes]:
    atual = validar_url_importavel(url)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain,application/pdf;q=0.8,*/*;q=0.2",
    }
    timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            resp = await client.get(atual)
            if resp.status_code in {301, 302, 303, 307, 308}:
                loc = resp.headers.get("location")
                if not loc:
                    raise URLImportError("Redirecionamento sem destino.")
                atual = validar_url_importavel(urljoin(atual, loc))
                continue

            content_type = resp.headers.get("content-type")
            if resp.status_code in {401, 403}:
                raise URLImportError(
                    "O site bloqueou a importação automática. Faça upload do arquivo ou cole o texto autorizado."
                )
            if resp.status_code >= 400:
                raise URLImportError(f"Falha ao importar URL: HTTP {resp.status_code}.")
            raw = resp.content[: MAX_URL_BYTES + 1]
            if len(raw) > MAX_URL_BYTES:
                raise URLImportError("Conteúdo da URL excede o limite permitido.")
            return atual, resp.status_code, content_type, raw

    raise URLImportError("Muitos redirecionamentos ao importar URL.")


def _decodificar(raw: bytes, content_type: str | None) -> str:
    charset = None
    if content_type:
        m = re.search(r"charset=([^;]+)", content_type, re.I)
        if m:
            charset = m.group(1).strip()
    for enc in [charset, "utf-8", "latin-1"]:
        if not enc:
            continue
        try:
            return raw.decode(enc, errors="ignore")
        except LookupError:
            continue
    return raw.decode("utf-8", errors="ignore")


async def importar_url_juridica(url: str, *, titulo: str | None = None) -> URLImportResult:
    """Busca URL pública e monta dossiê jurídico.

    Não grava em banco. O chamador decide se usa como conhecimento, documento ou
    entrada de análise estratégica, sempre com revisão humana.
    """
    url_original = _limpar_url(url)
    try:
        url_final, status, content_type, raw = await _fetch_bytes_seguro(url_original)
    except URLImportError as exc:
        return URLImportResult(
            url_original=url_original,
            url_final=url_original,
            status_code=0,
            content_type=None,
            titulo=titulo,
            descricao=None,
            texto="",
            dossie="",
            bloqueado=True,
            aviso=str(exc),
            metadados={"fonte": "url", "erro": type(exc).__name__},
        )

    ct = (content_type or "").lower()
    if "html" in ct or "xml" in ct or not ct or "text/" in ct:
        html = _decodificar(raw, content_type)
        titulo_html, descricao, canonical, texto = extrair_html_simples(html, url_final)
        titulo_final = titulo or titulo_html or urlparse(url_final).netloc
        if not texto or len(texto.strip()) < 40:
            return URLImportResult(
                url_original=url_original,
                url_final=url_final,
                status_code=status,
                content_type=content_type,
                titulo=titulo_final,
                descricao=descricao,
                texto="",
                dossie="",
                bloqueado=True,
                aviso="A página foi acessada, mas não havia texto útil suficiente para importar.",
                metadados={"canonical": canonical},
            )
        dossie = montar_dossie_documental(texto, titulo=titulo_final)
        return URLImportResult(
            url_original=url_original,
            url_final=canonical or url_final,
            status_code=status,
            content_type=content_type,
            titulo=titulo_final,
            descricao=descricao,
            texto=texto,
            dossie=dossie,
            bloqueado=False,
            aviso="Conteúdo importado como referência jurídica. Revise antes de usar no caso.",
            metadados={"canonical": canonical, "bytes": len(raw), "chars": len(texto)},
        )

    return URLImportResult(
        url_original=url_original,
        url_final=url_final,
        status_code=status,
        content_type=content_type,
        titulo=titulo or urlparse(url_final).netloc,
        descricao=None,
        texto="",
        dossie="",
        bloqueado=True,
        aviso="Tipo de conteúdo ainda não suportado para importação por URL. Faça upload do arquivo no GED.",
        metadados={"bytes": len(raw)},
    )
