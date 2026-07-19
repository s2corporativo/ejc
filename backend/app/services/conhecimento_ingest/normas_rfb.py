# ── app/services/conhecimento_ingest/normas_rfb.py ───────────────────────────
# Fonte Normas RFB → RAG: atos normativos tributários (IN, ADI, Soluções de
# Consulta COSIT...) via busca por querystring do sijut2consulta — sem API
# oficial, mas com querystring parametrizável estável (sondagem
# docs/CATALOGO_APIS_EJC.md: "Normas RFB OK").
#
# Estratégia:
#   1. Para cada termo de NORMAS_RFB_TERMOS (.env, CSV; default = lista curta
#      derivada do ramo tributário do escritório), GET
#      consulta.action?termoBusca=<termo> e parseia a lista de resultados
#      (âncoras com idAto).
#   2. Para cada ato: GET link.action?visao=anotado&idAto=<id> (página de
#      visualização), HTML → texto, upsert_documento com chave
#      `rfb:<tipo>:<numero>:<ano>` (fallback determinístico `rfb:ato:<idAto>`
#      quando o título não segue o padrão), confiança ALTA, categoria
#      legislacao_tributaria.
#
# Educação com o portal: teto de MAX_DOCS_POR_EXECUCAO atos por execução e
# pausa de PAUSA_S entre downloads. Tolerância total: termo/ato fora do padrão
# → warning e pula; a fonte nunca levanta para o orquestrador.
from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.conhecimento_ingest.base import (
    limpar_html, html_para_texto, slugificar, texto_normalizado,
)
from app.services.ingestion_service import fetch, upsert_documento

logger = logging.getLogger("ejc.conhecimento.normas_rfb")

BASE = "https://normas.receita.fazenda.gov.br/sijut2consulta"

# Termos padrão — ramo tributário atendido pelo escritório (Betim/MG).
# Sobrescrevível via NORMAS_RFB_TERMOS (.env, CSV).
TERMOS_PADRAO = [
    "Solução de Consulta ISS",
    "IRPF",
    "Simples Nacional",
    "PIS COFINS",
]

MAX_DOCS_POR_EXECUCAO = 20   # teto de atos processados por execução
MIN_CONTEUDO = 200           # texto menor = página de erro/navegação
PAUSA_S = 1.0                # pausa educada entre downloads (exigência da missão)

# Âncora de resultado: qualquer link *.action com idAto=<n> (o sijut2consulta
# varia entre link.action/visualizar.action conforme a visão).
_RE_RESULTADO = re.compile(
    r'<a\b[^>]*?href\s*=\s*"[^"]*?\.action\?[^"]*?idAto=(\d+)[^"]*"[^>]*>(.*?)</a>',
    re.S | re.I,
)
# Título normalizado no padrão "instrucao normativa rfb no 2110, de ... 2022"
# (após texto_normalizado, "nº" NFKD-decompõe para "no").
_RE_TIPO_NUM = re.compile(r"^(?P<tipo>[a-z][a-z\s]*?)\s+n[o.]?\s*\.?\s*(?P<num>\d[\d.]*)")
_RE_ANO = re.compile(r"\b((?:19|20)\d{2})\b")


def _termos(cfg) -> list[str]:
    csv = (getattr(cfg, "NORMAS_RFB_TERMOS", "") or "").strip()
    if csv:
        return [t.strip() for t in csv.split(",") if t.strip()]
    return TERMOS_PADRAO


def parse_resultados(html: str) -> list[dict]:
    """Lista de resultados da consulta → [{"id_ato", "titulo"}], dedup por id.

    Tolerante: HTML fora do padrão → lista vazia (chamador loga e pula).
    """
    vistos: set[str] = set()
    atos: list[dict] = []
    for id_ato, rotulo in _RE_RESULTADO.findall(html or ""):
        titulo = limpar_html(rotulo)
        if len(titulo) < 10 or id_ato in vistos:
            continue   # âncora de paginação/ícone
        vistos.add(id_ato)
        atos.append({"id_ato": id_ato, "titulo": titulo})
    return atos


def _chave(titulo: str, id_ato: str) -> str:
    """chave_origem `rfb:<tipo>:<numero>:<ano>` extraída do título do ato.

    Ex.: "Instrução Normativa RFB nº 2110, de 17 de outubro de 2022"
         → "rfb:instrucao-normativa-rfb:2110:2022".
    Título fora do padrão → fallback determinístico `rfb:ato:<idAto>`.
    """
    norm = texto_normalizado(titulo)
    m = _RE_TIPO_NUM.match(norm)
    anos = _RE_ANO.findall(norm)
    if m and anos:
        tipo = slugificar(m.group("tipo"), max_len=60)
        numero = m.group("num").replace(".", "")
        return f"rfb:{tipo}:{numero}:{anos[-1]}"
    return f"rfb:ato:{id_ato}"


def _url_ato(id_ato: str) -> str:
    return f"{BASE}/link.action?visao=anotado&idAto={id_ato}"


async def ingerir(db: AsyncSession) -> dict:
    """Busca por termos tributários no sijut2consulta e ingere os atos no RAG.

    Retorna {"novos", "atualizados", "inalterados", "erros"} — contrato do
    orquestrador. Commit POR ato; erro isolado nunca derruba a fonte.
    """
    cfg = get_settings()
    resumo = {"novos": 0, "atualizados": 0, "inalterados": 0, "erros": 0}
    processados = 0
    vistos: set[str] = set()

    for termo in _termos(cfg):
        if processados >= MAX_DOCS_POR_EXECUCAO:
            break
        try:
            r = await fetch(
                f"{BASE}/consulta.action",
                params={"termoBusca": termo, "p": "1"},
                headers={"Accept": "text/html"},
                timeout=45,
                validar_ssrf=True,
            )
            atos = parse_resultados(r.text)
        except Exception as e:   # portal fora do ar/HTML mudou → pula o termo
            resumo["erros"] += 1
            logger.warning("RFB termo %r: %s: %s", termo, type(e).__name__, e)
            continue
        if not atos:
            logger.warning("RFB termo %r: nenhum resultado parseado "
                           "(layout mudou?)", termo)
            continue

        for ato in atos:
            if processados >= MAX_DOCS_POR_EXECUCAO:
                break
            chave = _chave(ato["titulo"], ato["id_ato"])
            if chave in vistos:
                continue
            vistos.add(chave)
            url = _url_ato(ato["id_ato"])
            try:
                rv = await fetch(url, headers={"Accept": "text/html"}, timeout=45,
                                 validar_ssrf=True)
                texto = html_para_texto(rv.text)
                if not texto or len(texto) < MIN_CONTEUDO:
                    logger.warning("RFB %s: conteúdo curto/vazio, pulado", chave)
                    continue
                res = await upsert_documento(
                    db,
                    titulo=ato["titulo"][:500],
                    categoria="legislacao_tributaria",
                    conteudo=texto,
                    chave_origem=chave,
                    fonte=url,                  # URL oficial do ato
                    # Conteúdo raspado (tolerante a layout) → confiança MEDIA
                    # (distingue de jurisprudência curada no gate de citação).
                    confianca="media",
                    extra={
                        "origem": "normas_rfb",
                        "proveniencia": "auto-scraped",
                        "termo_busca": termo,
                        "id_ato": ato["id_ato"],
                        "titulo_original": ato["titulo"][:300],
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
            except Exception as e:   # ato problemático nunca derruba a fonte
                await db.rollback()
                resumo["erros"] += 1
                logger.warning("RFB %s: %s: %s", chave, type(e).__name__, e)
                continue
            await asyncio.sleep(PAUSA_S)        # educação com o portal
        logger.info("RFB termo %r: %d processado(s) até aqui — %s",
                    termo, processados, resumo)
    return resumo
