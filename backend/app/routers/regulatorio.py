"""
Digest regulatorio semanal (consolidacao 28/06/2026).
Agrega DADOS REAIS ja coletados pela prod (tabela diario_oficial_alertas,
populada pelo scheduler que monitora DOU/DOE-MG) — sem mock, sem tabela nova.
Substitui de forma honesta o objetivo do mock "legislacao_dinamica".
Montado em /api/regulatorio (contrato público /api/v1/regulatorio via middleware).
"""
from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user

router = APIRouter(
    prefix="/regulatorio",
    tags=["regulatorio"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/digest-semanal")
async def digest_semanal(
    dias: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Resumo dos alertas regulatorios (Diario Oficial) dos ultimos N dias,
    agregados por fonte e por palavra-chave."""
    desde = datetime.utcnow() - timedelta(days=dias)
    rows = (await db.execute(text("""
        SELECT fonte, keyword_match, titulo, resumo, link, data_publicacao, lido
        FROM diario_oficial_alertas
        WHERE created_at >= :desde
        ORDER BY data_publicacao DESC NULLS LAST, created_at DESC
        LIMIT 300
    """), {"desde": desde})).mappings().all()

    por_fonte: Dict[str, int] = {}
    por_keyword: Dict[str, int] = {}
    nao_lidos = 0
    itens = []
    for r in rows:
        f = r["fonte"] or "—"
        por_fonte[f] = por_fonte.get(f, 0) + 1
        if r["keyword_match"]:
            por_keyword[r["keyword_match"]] = por_keyword.get(r["keyword_match"], 0) + 1
        if not r["lido"]:
            nao_lidos += 1
        if len(itens) < 30:
            itens.append({
                "fonte": r["fonte"],
                "keyword": r["keyword_match"],
                "titulo": r["titulo"],
                "resumo": (r["resumo"][:280] + "...") if r["resumo"] and len(r["resumo"]) > 280 else r["resumo"],
                "link": r["link"],
                "data_publicacao": str(r["data_publicacao"]) if r["data_publicacao"] else None,
            })

    return {
        "periodo_dias": dias,
        "desde": desde.date().isoformat(),
        "total_alertas": len(rows),
        "nao_lidos": nao_lidos,
        "por_fonte": por_fonte,
        "top_keywords": sorted(
            [{"keyword": k, "qtd": v} for k, v in por_keyword.items()],
            key=lambda x: -x["qtd"],
        )[:15],
        "itens_recentes": itens,
        "fonte_dados": "diario_oficial_alertas (DOU/DOE-MG — coleta real do scheduler)",
    }
