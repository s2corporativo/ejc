"""
citation_check.py — Verificador anti-alucinação de citações (#46).

Extrai súmulas e artigos citados num texto (peça/parecer gerado por IA) e
confirma CADA UM contra o RAG (base oficial já ingerida: ~1.500 súmulas STF/STJ/TST
+ códigos). Citações NÃO confirmadas são sinalizadas para verificação manual (OAB).

VERIFICAÇÃO = lookup EXATO (chave_origem / título), não busca semântica — porque
verificar existência exige precisão, não similaridade. 100% local (sem IA externa).
"""
from __future__ import annotations

from sqlalchemy import text

# Os padrões de extração (súmula/artigo/nº CNJ/recursos/menções vagas) vivem em
# app/services/verificador_jurisprudencia.py — este módulo mantém apenas os
# lookups exatos no RAG oficial (_existe_sumula/_existe_artigo) e a fachada
# retrocompatível verificar_citacoes().


async def _existe_sumula(db, num: str, orgao: str) -> str | None:
    """Lookup exato por chave_origem (ingestão nova) + fallback por título."""
    keys = [f"sumula:{orgao}:{num}"] if orgao else \
           [f"sumula:{t}:{num}" for t in ("STF", "STJ", "TST")]
    row = (await db.execute(text(
        "SELECT titulo FROM knowledge_docs "
        "WHERE deleted_at IS NULL AND chave_origem = ANY(:k) LIMIT 1"
    ), {"k": keys})).first()
    if row:
        return row[0]
    # Fallback p/ docs de formato antigo: título "Súmula N ..." (boundary via ' %')
    params = {"t": f"Súmula {num} %"}
    cond = ""
    if orgao:
        cond = " AND titulo ILIKE :org"
        params["org"] = f"%{orgao}%"
    row = (await db.execute(text(
        "SELECT titulo FROM knowledge_docs WHERE deleted_at IS NULL "
        "AND categoria LIKE 'sumula%' AND titulo ILIKE :t" + cond + " LIMIT 1"
    ), params)).first()
    return row[0] if row else None


async def _existe_artigo(db, num: str) -> str | None:
    """Procura o artigo no conteúdo da legislação ingerida (códigos no RAG)."""
    row = (await db.execute(text(
        "SELECT kd.titulo FROM knowledge_chunks kc "
        "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
        "WHERE kd.deleted_at IS NULL AND kd.categoria = 'legislacao' "
        "AND (kc.conteudo ILIKE :a1 OR kc.conteudo ILIKE :a2) LIMIT 1"
    ), {"a1": f"%Art. {num} %", "a2": f"%Art. {num}º%"})).first()
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
