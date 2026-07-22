# ── app/services/ingestors/lexml.py ──────────────────────────────────────────
# Ingestor FEDERADO LexML → RAG (legislação + jurisprudência, agendado por temas).
#
# Por que LexML como VEÍCULO de volume: o LexML.gov.br (Rede de Informação
# Legislativa e Jurídica, mantida pelo Senado) é o federador oficial que expõe,
# NUMA ÚNICA fonte pública, legislação federal/ESTADUAL (ALMG)/MUNICIPAL (Betim)
# e jurisprudência de TJ/TRT/TRF/TST/STJ/STF. Em vez de escrever um scraper
# dedicado (e não-testável aqui) para cada portal heterogêneo — ALMG, Câmara de
# Betim, TRT-3, TRF-6 diretos —, este ingestor reaproveita o caminho JÁ PROVADO
# `jurisprudencia_externa.buscar_lexml` (API pública, keyword-based) e federa
# tudo por PALAVRAS que miram as autoridades e as áreas do escritório (Betim/MG).
#
# ESPELHA a estrutura do ingestor TJMG (tjmg.py): catálogo de temas curados →
# busca best-effort por tema → upsert idempotente com dedup por chave_origem →
# métricas (novos, total). Falha de rede/fonte NUNCA derruba a execução.
#
# COBERTURA (honesta): a busca do LexML é por TERMOS (não há parâmetro de
# "autoridade" na assinatura de buscar_lexml). Miramos os tribunais/casas/
# localidades pelas próprias PALAVRAS do tema (ex.: "TRT-3 horas extras",
# "ALMG lei estadual Minas Gerais", "Betim lei municipal"). O que o federador
# devolve é exatamente o que entra — nada é fabricado. Portais DEDICADOS (ALMG,
# leis municipais de Betim, TRT/TRF diretos) exigiriam build verificável com
# .gov liberado e ficam como follow-up documentado (.env.example) — não se
# inventa endpoint aqui.
#
# GOVERNANÇA / CITATION GATE: jurisprudência entra em categoria "jurisprudencia"
# (conteúdo público/global, client_id/case_id = NULL). A legislação federada
# entra em categoria "referencia_legislativa" — deliberadamente FORA do prefixo
# "legislacao%" —, porque o gate anti-alucinação de citações
# (citation_check._existe_artigo) confia em `categoria LIKE 'legislacao%'` como
# prova de que um ARTIGO existe: os registros do LexML são EMENTAS/índices de
# norma (título + resumo), não a lei seca verbatim, e alimentá-los ali afrouxaria
# o gate (números de artigo passariam a "existir" via ementa alheia). A busca
# semântica default (categorias=None) varre TODAS as categorias, então esses
# documentos seguem recuperáveis normalmente — só não contaminam o gate.
from __future__ import annotations

import hashlib
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.ingestion_service import upsert_documento
from app.services.jurisprudencia_externa import buscar_lexml

logger = logging.getLogger("ejc.ingestao.lexml")

# Categorias RAG por tipo LexML. Ver nota de GOVERNANÇA no topo: legislação
# federada é "referencia_legislativa" (NÃO 'legislacao%') para não afrouxar o
# citation gate; jurisprudência é 'jurisprudencia' (o gate de súmula usa
# 'sumula%', então não há colisão).
_CATEGORIA = {"legislacao": "referencia_legislativa", "jurisprudencia": "jurisprudencia"}
_TIPO_FONTE = {"legislacao": "legislacao_referencia", "jurisprudencia": "jurisprudencia_oficial"}

# Os dois tipos que o federador cobre e que este ingestor varre por tema.
TIPOS = ("legislacao", "jurisprudencia")

# ══════════════════════════════════════════════════════════════════════════
# Catálogo de TEMAS/autoridades — palavras-chave que miram as jurisdições-alvo
# do escritório (Betim/MG) e suas áreas. Cada tema é buscado para tipo=
# 'legislacao' E tipo='jurisprudencia' (temas de tribunal rendem mais na
# jurisprudência; temas de casa/localidade rendem mais na legislação — a busca
# degrada graciosamente quando um tipo não casa). Sobrescrevível via
# LEXML_INGEST_TEMAS (.env, CSV).
# ══════════════════════════════════════════════════════════════════════════
TEMAS_PADRAO = [
    # ── Tribunais estaduais/regionais MG (jurisdição direta do escritório) ──
    "TJMG dano moral consumidor",
    "TJMG usucapião imóvel",
    "TRT-3 horas extras verbas rescisórias",          # trabalhista MG
    "TRT-3 vínculo empregatício reconhecimento",
    "TRF-6 benefício previdenciário INSS",            # federal MG (6ª região)
    "TRF-1 servidor público federal concurso",        # federal (1ª região)
    # ── Tribunais superiores ──
    "TST justa causa rescisão contrato de trabalho",
    "STJ recurso repetitivo direito do consumidor",
    "STF repercussão geral direito administrativo",
    # ── Juizados especiais (JEC / JEF) ──
    "juizado especial cível negativação indevida",
    "juizado especial federal previdenciário revisão",
    # ── Legislação estadual (ALMG) e municipal (Betim) via localidade ──
    "ALMG lei estadual Minas Gerais servidor público",
    "Minas Gerais ICMS lei estadual tributária",
    "Betim lei municipal",
    "Betim plano diretor código de obras município",
    "lei municipal IPTU ISS código tributário municipal",
    # ── Áreas nucleares do escritório (federa federal + estadual + municipal) ──
    "improbidade administrativa licitação contrato público",
    "meio ambiente licenciamento infração ambiental",
    "direito do consumidor plano de saúde negativa de cobertura",
    "família alimentos guarda divórcio partilha",
    "recuperação judicial falência empresarial",
    "aposentadoria revisão benefício previdenciário",
    "locação despejo imobiliário",
    "responsabilidade civil indenização dano moral",
]


def _temas(cfg) -> list[str]:
    csv = (getattr(cfg, "LEXML_INGEST_TEMAS", "") or "").strip()
    if csv:
        return [t.strip() for t in csv.split(",") if t.strip()]
    return TEMAS_PADRAO


def _chave(item: dict, tipo: str) -> str:
    """Chave de dedup idempotente, namespaced por tipo (leg/jur) para que um
    mesmo URN não colida entre a face legislação e a face jurisprudência.
    Prefere o identificador do LexML (URN, já sem o prefixo 'urn:lex:br:' e
    limitado a 80 chars por buscar_lexml); sem ele, usa hash estável de
    título+ementa (mesmo registro não duplica entre execuções)."""
    ns = tipo[:3]                                   # 'leg' | 'jur'
    ident = (item.get("numero_acordao") or "").strip()
    if ident:
        return f"lexml:{ns}:{ident}"[:120]
    base = ((item.get("titulo") or "") + "|" + (item.get("ementa") or ""))[:500]
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"lexml:{ns}:{h}"


def _monta_conteudo(item: dict, tipo: str) -> str:
    """Concatena as partes citáveis do registro LexML (título + metadados +
    ementa/resumo). Não inventa texto: usa só o que o federador retornou."""
    partes: list[str] = []
    if item.get("titulo"):
        partes.append(item["titulo"])
    if tipo == "jurisprudencia" and item.get("tribunal"):
        partes.append(f"Tribunal: {item['tribunal']}")
    if item.get("relator"):
        rotulo = "Relator(a)/Autor" if tipo == "jurisprudencia" else "Autoridade/Autor"
        partes.append(f"{rotulo}: {item['relator']}")
    if item.get("data_julgamento"):
        partes.append(f"Data: {item['data_julgamento']}")
    if item.get("area_juridica"):
        partes.append(f"Área: {item['area_juridica']}")
    if item.get("ementa"):
        partes.append(f"\n{item['ementa']}")
    return "\n".join(partes)


async def ingerir(db: AsyncSession) -> tuple[int, int]:
    """Varre o catálogo de temas no LexML (tipo='legislacao' e 'jurisprudencia')
    e ingere os registros no RAG. Retorna (novos, total_processados) — assinatura
    exigida por `ingestion_service.executar_ingestao`.

    Best-effort: erro de rede/fonte num tema/tipo é logado e pulado (nunca
    derruba a execução). Commit por item + dedup intra-execução por chave_origem.
    """
    cfg = get_settings()
    temas = _temas(cfg)
    max_item = int(getattr(cfg, "LEXML_INGEST_MAX_POR_TEMA", 20) or 20)

    novos = total = 0
    vistas: set[str] = set()   # dedup intra-execução (mesmo registro em 2 temas/tipos)

    for tema in temas:
        for tipo in TIPOS:
            try:
                itens = await buscar_lexml(tema, tipo=tipo, por_pagina=max_item)
            except Exception as e:   # rede/XML — nunca derruba a execução inteira
                logger.warning("LexML %s %r: %s: %s", tipo, tema, type(e).__name__, e)
                continue

            categoria = _CATEGORIA[tipo]
            n_tema = 0
            for it in itens:
                ementa = it.get("ementa") or ""
                if len(ementa) < 50:
                    continue   # sem valor semântico
                chave = _chave(it, tipo)
                if chave in vistas:
                    continue
                vistas.add(chave)

                try:
                    res = await upsert_documento(
                        db,
                        titulo=(it.get("titulo") or f"LexML {tipo}")[:500],
                        categoria=categoria,
                        conteudo=_monta_conteudo(it, tipo),
                        chave_origem=chave,
                        fonte=it.get("link_original") or "LexML.gov.br (federador oficial)",
                        # tribunal só na face jurisprudência (metadado do julgado)
                        tribunal=(it.get("tribunal") or None) if tipo == "jurisprudencia" else None,
                        extra={
                            "tipo_lexml": tipo,
                            "tribunal": it.get("tribunal") if tipo == "jurisprudencia" else None,
                            "relator": it.get("relator"),
                            "data": it.get("data_julgamento"),
                            "area_juridica": it.get("area_juridica"),
                            "link": it.get("link_original"),
                            "urn": it.get("numero_acordao"),
                            "tema_busca": tema,
                            "origem": "lexml",
                            "rag_status": "aprovado",
                            "tipo_fonte": _TIPO_FONTE[tipo],
                        },
                        confianca="alta",   # federador oficial (Senado/LexML)
                    )
                    # Commit por item: métricas contam só o persistido; um erro
                    # isolado dá rollback APENAS do item falho.
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    logger.warning("LexML upsert %r: %s: %s", chave, type(e).__name__, e)
                    continue

                total += 1
                if res in ("novo", "atualizado"):
                    novos += 1
                    n_tema += 1

            logger.info("LexML %s %r: %d novos / %d itens", tipo, tema, n_tema, len(itens))

    return novos, total
