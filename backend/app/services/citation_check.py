"""
citation_check.py — Verificador anti-alucinação de citações (#46).

Extrai súmulas e artigos citados num texto (peça/parecer gerado por IA) e
confirma CADA UM contra o RAG (base oficial ingerida: súmulas conferidas
STF/STJ/TST + legislação federal do Planalto; o VOLUME depende dos seeds e dos
ingestores habilitados — ver base_juridica_seed.py e os ingestores opt-in em
services/ingestors/). Citações NÃO confirmadas são sinalizadas para verificação
manual (OAB); com CITACOES_MODO_ESTRITO=true, súmula/artigo ausente da base
passa a BLOQUEAR.

VERIFICAÇÃO = lookup EXATO (chave_origem / título), não busca semântica — porque
verificar existência exige precisão, não similaridade. 100% local (sem IA externa).
"""
from __future__ import annotations

import re

from sqlalchemy import text

# Os padrões de extração (súmula/artigo/nº CNJ/recursos/menções vagas) vivem em
# app/services/verificador_jurisprudencia.py — este módulo mantém apenas os
# lookups exatos no RAG oficial (_existe_sumula/_existe_artigo) e a fachada
# retrocompatível verificar_citacoes().


async def _existe_sumula(db, num: str, orgao: str) -> str | None:
    """Lookup exato por chave_origem (ingestão nova) + fallback por título."""
    from app.services.ai_service import _filtros_gate_rag
    orgao_norm = (orgao or "").strip().lower()
    keys = [f"sumula:{orgao_norm}:{num}"] if orgao_norm else \
           [f"sumula:{t}:{num}" for t in ("stf", "stj", "tst")]
    row = (await db.execute(text(
        "SELECT kd.titulo FROM knowledge_docs kd "
        "WHERE kd.deleted_at IS NULL AND kd.vigente = TRUE "
        "AND kd.chave_origem = ANY(:k) " + _filtros_gate_rag(False) + " LIMIT 1"
    ), {"k": keys})).first()
    if row:
        return row[0]
    # Fallback p/ docs de formato antigo: título "Súmula N ..." (boundary via ' %')
    params = {"t": f"Súmula {num} %"}
    cond = ""
    if orgao_norm:
        cond = " AND kd.tribunal = :org"
        params["org"] = orgao_norm.upper()
    row = (await db.execute(text(
        "SELECT kd.titulo FROM knowledge_docs kd WHERE kd.deleted_at IS NULL "
        "AND kd.vigente = TRUE AND (kd.categoria LIKE 'sumula%' "
        "OR kd.chave_origem LIKE 'sumula:%') AND kd.titulo ILIKE :t" + cond + " " +
        _filtros_gate_rag(False) + " LIMIT 1"
    ), params)).first()
    return row[0] if row else None


# Sigla de código → slug do ingestor oficial (planalto.CATALOGO). O lookup de
# artigo fica RESTRITO ao doc desse diploma via chave_origem.
_SLUG_POR_DIPLOMA = {
    "cf": "cf88", "cpc": "cpc", "cc": "cc", "clt": "clt",
    "cdc": "cdc", "cpp": "cpp", "cp": "cp", "ctn": "ctn",
}


async def _existe_artigo(db, num: str, diploma: str | None = None) -> str | None:
    """Procura o artigo no conteúdo da legislação ingerida, RESTRITO ao diploma
    citado (auditoria 2026-07-26, AI-056): buscar 'Art. N' em QUALQUER doc de
    categoria legislação podia confirmar a lei ERRADA — um "art. 5º da Lei X"
    era validado porque o art. 5º existe na CF ou em outra lei qualquer.

    `diploma`: sigla de código ("CF", "CPC", "CDC"…) ou "Lei nº 8.078/90".
    Sem diploma identificável, NÃO confirma (None → verificação manual/OAB) —
    fail-closed: confirmação ambígua vale menos que nenhuma."""
    from app.services.ai_service import _filtros_gate_rag
    d = (diploma or "").strip().lower()
    cond = ""
    params: dict = {"a1": f"%Art. {num} %", "a2": f"%Art. {num}º%"}
    if d in _SLUG_POR_DIPLOMA:
        cond = "AND kd.chave_origem = :chave "
        params["chave"] = f"planalto:{_SLUG_POR_DIPLOMA[d]}"
    elif d.startswith("lei"):
        # "lei nº 8.078/90" → número puro "8078"; casa o título canônico
        # ("… (Lei 8.078/1990)") com os pontos de milhar removidos.
        numeros = re.sub(r"\D", "", d.split("/")[0])
        if not numeros:
            return None
        cond = "AND replace(kd.titulo, '.', '') ILIKE :lei "
        params["lei"] = f"%lei {numeros}/%"
    else:
        # Diploma ausente/desconhecido: nunca confirmar contra a lei errada.
        return None
    row = (await db.execute(text(
        "SELECT kd.titulo FROM knowledge_chunks kc "
        "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
        "WHERE kd.deleted_at IS NULL AND kd.vigente = TRUE "
        "AND kd.categoria LIKE 'legislacao%' " + cond +
        "AND (kc.conteudo ILIKE :a1 OR kc.conteudo ILIKE :a2) " +
        _filtros_gate_rag(False) + " LIMIT 1"
    ), params)).first()
    return row[0] if row else None


async def verificar_citacoes(
    db, texto: str, *, consultar_datajud: bool = False,
) -> dict:
    """Relatório de verificação das citações encontradas no texto.

    Desde a promoção ao VERIFICADOR RIGOROSO (verificador_jurisprudencia),
    delega ao novo módulo — que mantém o shape legado (total/confirmadas/
    nao_encontradas/citacoes[{citacao,tipo,encontrada,fonte}]/aviso) e o
    ESTENDE com status por citação (verificada/identificada/suspeita/generica),
    score 0-100, avisos e campos estruturados (tribunal/numero/orgao/relator/
    data). `consultar_datajud=True` confirma números CNJ no DataJud (opt-in,
    fail-safe, máx. 5 consultas por verificação).
    """
    from app.services.verificador_jurisprudencia import verificar_jurisprudencia
    return await verificar_jurisprudencia(
        db, texto, consultar_datajud=consultar_datajud)
