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
    # A ingestão grava o tribunal em MINÚSCULO na chave (sumula:tst:331 —
    # ver sumulas_ingestion). Aceita ambos os casos para cobrir dados legados;
    # sem isso o verbete seedado nunca atingia status "verificada".
    orgaos = [orgao] if orgao else ["STF", "STJ", "TST"]
    keys = [f"sumula:{t}:{num}" for o in orgaos for t in (o, o.lower())]
    row = (await db.execute(text(
        "SELECT titulo FROM knowledge_docs "
        "WHERE deleted_at IS NULL AND chave_origem = ANY(:k) LIMIT 1"
    ), {"k": keys})).first()
    if row:
        return row[0]
    # Fallback por título: a ingestão atual grava "Súmula TST nº 331" (ou
    # "Súmula Vinculante STF nº N") com fonte='sumula' e categoria=ÁREA
    # (trabalhista/...); docs de formato antigo usam título "Súmula N ..."
    # com categoria 'sumula%'. Cobre os dois formatos.
    params = {"t1": f"Súmula {num} %", "t2": f"Súmula %nº {num}"}
    cond = ""
    if orgao:
        cond = " AND titulo ILIKE :org"
        params["org"] = f"%{orgao}%"
    row = (await db.execute(text(
        "SELECT titulo FROM knowledge_docs WHERE deleted_at IS NULL "
        "AND (categoria LIKE 'sumula%' OR fonte = 'sumula') "
        "AND (titulo ILIKE :t1 OR titulo ILIKE :t2)" + cond + " LIMIT 1"
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
