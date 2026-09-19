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
# Sobrescrevível via NORMAS_RFB_TERMOS (.env, CSV). Ordem importa: um termo com
# muitos resultados pode sozinho esgotar MAX_DOCS_POR_EXECUCAO e os termos
# seguintes nem chegam a ser consultados nesta execução (ver
# test_ingerir_rfb_teto_de_docs) — os termos da reforma tributária vêm cedo na
# lista para não ficarem permanentemente famintos atrás dos demais.
TERMOS_PADRAO = [
    "Reforma Tributária IBS CBS",
    "LC 214/2025",
    "Solução de Consulta ISS",
    "IRPF",
    "Simples Nacional",
    "PIS COFINS",
]

MAX_DOCS_POR_EXECUCAO = 20   # teto de atos processados por execução
MIN_CONTEUDO = 200           # texto menor = página de erro/navegação
PAUSA_S = 1.0                # pausa educada entre downloads (exigência da missão)

# O portal mantém dois formatos observados:
# 1) legado: link.action?...idAto=<n>;
# 2) atual (2026): tabela <tr class="linhaResultados"> cujo href aponta para
#    normasinternet2.receita.fazenda.gov.br/#/consulta/externa/<id>/...
# O parser aceita ambos e remove comentários HTML antes de procurar resultados,
# evitando ressuscitar links antigos comentados no template.
_RE_COMMENT = re.compile(r"<!--.*?-->", re.S)
_RE_RESULTADO_LEGADO = re.compile(
    r"<a\b[^>]*?href\s*=\s*(['\"])[^'\"]*?\.action\?[^'\"]*?"
    r"idAto=(\d+)[^'\"]*?\1[^>]*>(.*?)</a>",
    re.S | re.I,
)
_RE_LINHA_RESULTADO = re.compile(
    r"<tr\b[^>]*class\s*=\s*(['\"])[^'\"]*\blinhaResultados\b[^'\"]*\1"
    r"[^>]*>(.*?)</tr>",
    re.S | re.I,
)
_RE_TD = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)
_RE_FONTE_ATUAL = re.compile(
    r"href\s*=\s*(['\"])"
    r"(https://normasinternet2\.receita\.fazenda\.gov\.br/"
    r"#/consulta/externa/(\d+)/[^'\"]*)\1",
    re.I,
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
    """Lista oficial de resultados RFB, compatível com layout legado e atual.

    No layout atual, a própria linha da busca traz tipo, número, órgão,
    publicação e ementa. Essa ementa é útil para descoberta, mas NÃO é tratada
    como inteiro teor; o ingestor grava a proveniência explicitamente.
    """
    bruto = _RE_COMMENT.sub(" ", html or "")
    vistos: set[str] = set()
    atos: list[dict] = []

    for _q, linha in _RE_LINHA_RESULTADO.findall(bruto):
        fonte_match = _RE_FONTE_ATUAL.search(linha)
        if not fonte_match:
            continue
        fonte_url = fonte_match.group(2)
        id_ato = fonte_match.group(3)
        if id_ato in vistos:
            continue
        colunas = _RE_TD.findall(linha)
        if len(colunas) < 5:
            continue
        tipo = limpar_html(colunas[0])
        numero = limpar_html(colunas[1])
        orgao = limpar_html(colunas[2])
        publicacao = limpar_html(colunas[3])
        ementa = limpar_html(colunas[4])
        if not tipo or not numero:
            continue
        tipo_titulo = tipo if orgao.casefold() in tipo.casefold() else f"{tipo} {orgao}".strip()
        titulo = f"{tipo_titulo} nº {numero}"
        if publicacao:
            titulo += f", de {publicacao}"
        vistos.add(id_ato)
        atos.append({
            "id_ato": id_ato,
            "titulo": titulo,
            "ementa": ementa,
            "fonte_url": fonte_url,
            "orgao": orgao,
            "publicacao": publicacao,
            "inteiro_teor": False,
        })

    # Compatibilidade com fixtures/links legados ainda existentes.
    for _q, id_ato, rotulo in _RE_RESULTADO_LEGADO.findall(bruto):
        if id_ato in vistos:
            continue
        titulo = limpar_html(rotulo)
        if len(titulo) < 10:
            continue
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
    orquestrador. Diagnóstico: a ÚLTIMA exceção engolida vai em
    "ultimo_erro_amostra" (tipo + mensagem, truncada) e zero atos brutos
    coletados na origem inteira marca "zero_brutos" — o orquestrador transforma
    ambos em `ultimo_erro` no painel (antes, falha aqui virava status "erro"
    com erro null: indiagnosticável).
    Commit POR ato; erro isolado nunca derruba a fonte.
    """
    cfg = get_settings()
    resumo = {"novos": 0, "atualizados": 0, "inalterados": 0, "erros": 0}
    processados = 0
    brutos = 0                   # atos reconhecidos nas listas de resultado
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
            resumo["ultimo_erro_amostra"] = \
                f"termo {termo!r}: {type(e).__name__}: {e}"[:300]
            logger.warning("RFB termo %r: %s: %s", termo, type(e).__name__, e)
            continue
        brutos += len(atos)
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
            url = ato.get("fonte_url") or _url_ato(ato["id_ato"])
            try:
                ementa = (ato.get("ementa") or "").strip()
                if ementa:
                    texto = (
                        "[PROVENIÊNCIA — RFB: EMENTA/RESUMO DA LISTAGEM OFICIAL, "
                        "NÃO É O INTEIRO TEOR. Consulte a fonte oficial antes de "
                        "fundamentar.]\n\n" + ementa
                    )
                    inteiro_teor = False
                    natureza_conteudo = "ementa_resultado_busca"
                else:
                    rv = await fetch(
                        url,
                        headers={"Accept": "text/html"},
                        timeout=45,
                        validar_ssrf=True,
                    )
                    texto = html_para_texto(rv.text)
                    inteiro_teor = True
                    natureza_conteudo = "inteiro_teor_html"
                if not texto or len(texto) < MIN_CONTEUDO:
                    logger.warning("RFB %s: conteúdo curto/vazio, pulado", chave)
                    continue
                res = await upsert_documento(
                    db,
                    titulo=ato["titulo"][:500],
                    categoria="legislacao_tributaria",
                    conteudo=texto,
                    chave_origem=chave,
                    fonte=url,
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
                        "inteiro_teor": inteiro_teor,
                        "natureza_conteudo": natureza_conteudo,
                        "consultar_inteiro_teor_em": url,
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
                resumo["ultimo_erro_amostra"] = \
                    f"{chave}: {type(e).__name__}: {e}"[:300]
                logger.warning("RFB %s: %s: %s", chave, type(e).__name__, e)
                continue
            await asyncio.sleep(PAUSA_S)        # educação com o portal
        logger.info("RFB termo %r: %d processado(s) até aqui — %s",
                    termo, processados, resumo)

    # Zero atos BRUTOS em TODOS os termos não é "sucesso": ou o portal caiu (a
    # amostra da exceção já explica) ou o HTML do sijut2consulta mudou e o
    # parser deixou de reconhecer os resultados. Sem esta marca, o parser
    # tolerante reportava sucesso com zero para sempre.
    if brutos == 0:
        resumo["zero_brutos"] = True
        resumo.setdefault(
            "ultimo_erro_amostra",
            "0 itens brutos na origem — layout pode ter mudado "
            "(nenhum resultado parseado no sijut2consulta para nenhum termo)",
        )
        logger.warning("RFB: 0 itens brutos na origem — layout pode ter mudado")
    return resumo
