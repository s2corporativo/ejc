# ── app/services/conhecimento_ingest/anpd.py ─────────────────────────────────
# Fonte ANPD → RAG: regulamentações (atos normativos) e guias orientativos da
# Autoridade Nacional de Proteção de Dados, publicados em páginas gov.br
# (Plone — listas de links estáveis; sondagem docs/CATALOGO_APIS_EJC.md:
# "ANPD OK, páginas gov.br estáveis").
#
# Estratégia (raspagem LEVE, sem dependência nova):
#   1. Baixa cada página-índice (regulamentações / guias e publicações).
#   2. Extrai âncoras que "parecem documento" (Resolução, Regulamento, Guia,
#      Orientação, Enunciado, Nota Técnica, Portaria... ou PDF direto).
#   3. Para cada link: HTML → texto do miolo (content-core) | PDF → extração
#      via ocr_service (PyMuPDF + OCR fallback, já existente no projeto).
#   4. upsert_documento com chave `anpd:<slug-da-url>` (idempotente/versionado),
#      confiança ALTA (fonte oficial), fonte = URL gov.br.
#
# Tolerância total: página/documento fora do padrão → warning e pula; teto de
# MAX_DOCS_POR_EXECUCAO documentos por execução (o job é semanal — o acervo
# completo converge em poucas execuções e depois vira "inalterado").
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from urllib.parse import urljoin, urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.conhecimento_ingest.base import (
    extrair_ancoras, html_para_texto, slugificar, texto_normalizado,
)
from app.services.ingestion_service import fetch, upsert_documento

logger = logging.getLogger("ejc.conhecimento.anpd")

# Páginas-índice oficiais (rotulo, categoria RAG, URL). Categorias NÃO
# restritas (fora de ai_service._RESTRICTED_CATS): conteúdo público/global.
PAGINAS = [
    (
        "regulamentacoes",
        "legislacao",
        "https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/"
        "atos-normativos/regulamentacoes_anpd",
    ),
    (
        "guias_orientativos",
        "doutrina",
        "https://www.gov.br/anpd/pt-br/centrais-de-conteudo/"
        "materiais-educativos-e-publicacoes",
    ),
]

MAX_DOCS_POR_EXECUCAO = 30      # teto de documentos processados por execução
MAX_PDF_BYTES = 15 * 1024 * 1024   # PDF acima disso é pulado (proteção memória)
MIN_CONTEUDO = 200              # texto menor que isso = página de navegação
PAUSA_S = 0.5                   # pausa educada entre downloads de documento

# Âncora "parece documento" quando o rótulo (normalizado, sem acento) contém:
_PALAVRAS_DOC = (
    "resolu", "regulament", "guia", "orientac", "enunciado",
    "nota tecnica", "portaria", "norma", "instrucao",
)
# Trechos de URL que são navegação/institucional — nunca documento:
_URL_IGNORAR = (
    "mailto:", "javascript:", "/noticias", "/composicao",
    "/canais_atendimento", "/pt-br/search", "/@@", "/login",
)


def extrair_links(html: str, url_base: str) -> list[dict]:
    """Âncoras da página-índice que apontam para documentos ANPD.

    Retorna [{"titulo", "url"}] dedupado por URL. Tolerante: HTML fora do
    padrão → lista vazia (o chamador loga e pula a página).
    """
    vistos: set[str] = set()
    links: list[dict] = []
    for href, rotulo in extrair_ancoras(html):
        url = urljoin(url_base, href)
        if not url.startswith(("http://", "https://")):
            continue
        if any(x in url for x in _URL_IGNORAR) or "#" in url:
            continue
        parte = urlparse(url)
        # Domínio oficial: casa "gov.br" exato ou subdomínio ".gov.br".
        # endswith("gov.br") sozinho casaria lookalike "malicioso-gov.br".
        if not (parte.netloc == "gov.br" or parte.netloc.endswith(".gov.br")):
            continue          # só domínio oficial
        eh_pdf = parte.path.lower().endswith(".pdf")
        eh_dou = parte.netloc == "in.gov.br" or parte.netloc.endswith(".in.gov.br")
        if not eh_pdf and "/anpd/" not in parte.path and not eh_dou:
            continue          # HTML: página da ANPD ou publicação oficial do DOU
        rot_norm = texto_normalizado(rotulo)
        if len(rot_norm) < 10:
            continue          # breadcrumb/ícone
        if not (eh_pdf or any(p in rot_norm for p in _PALAVRAS_DOC)):
            continue
        if url in vistos:
            continue
        vistos.add(url)
        links.append({"titulo": rotulo, "url": url})
    return links


def _chave(url: str) -> str:
    """chave_origem `anpd:<slug>` derivada do último segmento do path."""
    caminho = urlparse(url).path.rstrip("/")
    seg = caminho.rsplit("/", 1)[-1]
    seg = re.sub(r"\.pdf$", "", seg, flags=re.I)
    slug = slugificar(seg)
    if not slug:   # URL atípica → hash estável (dedup preservado)
        slug = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return f"anpd:{slug}"


def _texto_pdf(raw: bytes) -> str:
    """Extração de PDF via infra existente (ocr_service). Sync (CPU-bound)."""
    from app.services.ocr_service import extrair_texto_pdf
    return extrair_texto_pdf(raw)["texto"]


async def _conteudo(url: str) -> str | None:
    """Baixa e extrai o texto do documento (HTML ou PDF). None = sem conteúdo."""
    if urlparse(url).path.lower().endswith(".pdf"):
        r = await fetch(url, headers={"Accept": "*/*"}, timeout=60, validar_ssrf=True)
        if len(r.content) > MAX_PDF_BYTES:
            logger.warning("ANPD: PDF muito grande (%d bytes), pulado: %s",
                           len(r.content), url)
            return None
        # extração é CPU-bound → thread para não travar o event loop
        return await asyncio.to_thread(_texto_pdf, r.content)
    r = await fetch(url, headers={"Accept": "text/html"}, timeout=30, validar_ssrf=True)
    return html_para_texto(r.text)


async def ingerir(db: AsyncSession) -> dict:
    """Raspagem leve das páginas oficiais da ANPD → RAG.

    Retorna {"novos", "atualizados", "inalterados", "erros"} — contrato do
    orquestrador (conhecimento_ingest.executar_ingest_conhecimento).
    Commit POR documento: erro isolado dá rollback só do item corrente.
    """
    resumo = {"novos": 0, "atualizados": 0, "inalterados": 0, "erros": 0}
    processados = 0
    vistos: set[str] = set()

    for rotulo, categoria, pagina in PAGINAS:
        if processados >= MAX_DOCS_POR_EXECUCAO:
            break
        try:
            r = await fetch(pagina, headers={"Accept": "text/html"}, timeout=30,
                            validar_ssrf=True)
            links = extrair_links(r.text, pagina)
        except Exception as e:   # página indisponível/fora do padrão → pula
            resumo["erros"] += 1
            logger.warning("ANPD página %r: %s: %s", rotulo, type(e).__name__, e)
            continue
        if not links:
            logger.warning("ANPD página %r: nenhum link de documento reconhecido "
                           "(layout mudou?)", rotulo)
            continue

        for link in links:
            if processados >= MAX_DOCS_POR_EXECUCAO:
                break
            chave = _chave(link["url"])
            if chave in vistos:
                continue
            vistos.add(chave)
            try:
                texto = await _conteudo(link["url"])
                if not texto or len(texto) < MIN_CONTEUDO:
                    logger.warning("ANPD %s: conteúdo curto/vazio, pulado", chave)
                    continue
                res = await upsert_documento(
                    db,
                    titulo=f"ANPD — {link['titulo']}"[:500],
                    categoria=categoria,
                    conteudo=texto,
                    chave_origem=chave,
                    fonte=link["url"],          # URL oficial gov.br
                    # Conteúdo raspado (tolerante a layout) → confiança MEDIA:
                    # o gate de citação distingue de jurisprudência/doutrina
                    # curada. Proveniência auto-scraped registrada no extra.
                    confianca="media",
                    extra={
                        "origem": "anpd",
                        "proveniencia": "auto-scraped",
                        "secao": rotulo,
                        "url": link["url"],
                        "titulo_original": link["titulo"][:300],
                        "rag_status": "aprovado",
                        "tipo_fonte": "norma_oficial",
                    },
                )
                await db.commit()               # durável antes do próximo item
                processados += 1
                if res == "novo":
                    resumo["novos"] += 1
                elif res == "atualizado":
                    resumo["atualizados"] += 1
                else:
                    resumo["inalterados"] += 1
            except Exception as e:   # doc problemático nunca derruba a fonte
                await db.rollback()
                resumo["erros"] += 1
                logger.warning("ANPD %s: %s: %s", chave, type(e).__name__, e)
                continue
            await asyncio.sleep(PAUSA_S)
        logger.info("ANPD %r: %d processado(s) até aqui — %s",
                    rotulo, processados, resumo)
    return resumo
