# ── app/services/ingestors/planalto.py ───────────────────────────────────────
# Ingestor dos códigos-núcleo da legislação federal (texto integral).
# Fonte: Planalto (HTML estático, latin-1). Não há API — scraping estruturado
# de um conjunto FECHADO e estável de URLs. Reprocessa diário, mas o UPSERT
# idempotente só re-embeda se o texto mudou (alteração legislativa).
#
# Estratégia de extração: BeautifulSoup → texto limpo → remoção de ruído de
# "texto compilado" (riscado/anotações), preservando a sequência dos artigos.
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion_service import fetch, upsert_documento, normalizar

logger = logging.getLogger("ejc.ingestao.planalto")

# Conjunto-núcleo: os diplomas mais citados na rotina do escritório.
# (slug curto p/ chave_origem · título canônico · URL compilada do Planalto)
CODIGOS: list[dict] = [
    {"slug": "cf88",  "titulo": "Constituição Federal de 1988",
     "url": "https://www.planalto.gov.br/ccivil_03/constituicao/constituicaocompilado.htm"},
    {"slug": "cc",    "titulo": "Código Civil (Lei 10.406/2002)",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm"},
    {"slug": "cpc",   "titulo": "Código de Processo Civil (Lei 13.105/2015)",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm"},
    {"slug": "clt",   "titulo": "Consolidação das Leis do Trabalho (DL 5.452/1943)",
     "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm"},
    {"slug": "cdc",   "titulo": "Código de Defesa do Consumidor (Lei 8.078/1990)",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"},
    {"slug": "cp",    "titulo": "Código Penal (DL 2.848/1940)",
     "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm"},
    {"slug": "cpp",   "titulo": "Código de Processo Penal (DL 3.689/1941)",
     "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm"},
    {"slug": "eca",   "titulo": "Estatuto da Criança e do Adolescente (Lei 8.069/1990)",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l8069compilado.htm"},
    {"slug": "l14133","titulo": "Lei de Licitações e Contratos (Lei 14.133/2021)",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm"},
    {"slug": "ctn",   "titulo": "Código Tributário Nacional (Lei 5.172/1966)",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm"},
]


def extrair_texto(html: str) -> str:
    """Extrai texto legível do HTML do Planalto, preservando a ordem dos artigos.

    - Remove <script>/<style>.
    - Usa get_text com separador de linha.
    - Limpa entidades, espaços de tabulação visual e linhas vazias excessivas.
    Função pura (sem rede/DB) → testável isoladamente.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    txt = soup.get_text("\n")
    # Normaliza NBSP e espaços de indentação visual do Planalto
    txt = txt.replace("\xa0", " ")
    # Junta linhas quebradas no meio de frase: "...consumidor,\n e" → "...consumidor, e"
    txt = re.sub(r"[ \t]+\n", "\n", txt)
    txt = re.sub(r"\n[ \t]+", "\n", txt)
    return normalizar(txt)


async def baixar_codigo(codigo: dict) -> str:
    """Baixa e extrai o texto de um diploma (rede, sem DB)."""
    r = await fetch(codigo["url"], timeout=40)
    # Planalto serve ISO-8859-1; força fallback (httpx não tem apparent_encoding)
    r.encoding = r.charset_encoding or "latin-1"
    return extrair_texto(r.text)


async def ingerir(db: AsyncSession) -> tuple[int, int]:
    """Ingere/atualiza todos os códigos-núcleo no RAG. Retorna (novos, total)."""
    novos = total = 0
    for cod in CODIGOS:
        total += 1
        try:
            texto = await baixar_codigo(cod)
            if len(texto) < 2000:
                logger.warning(f"{cod['slug']}: texto suspeito ({len(texto)} chars) — pulado")
                continue
            res = await upsert_documento(
                db,
                titulo=cod["titulo"],
                categoria="legislacao",
                conteudo=texto,
                chave_origem=f"planalto:{cod['slug']}",
                fonte=cod["url"],
                extra={"diploma": cod["slug"], "origem": "planalto"},
                confianca="alta",   # fonte oficial (Planalto — texto de lei)
            )
            if res in ("novo", "atualizado"):
                novos += 1
            # commit incremental: um diploma grande não bloqueia os demais
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.warning(f"Planalto {cod['slug']}: {type(e).__name__}: {e}")
    return novos, total
