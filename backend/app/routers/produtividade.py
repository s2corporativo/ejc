"""Produtividade — GET /analytics/produtividade?periodo=7d|30d|90d|365d
   Horas (time_entries) por advogado e por área. Alimenta Produtividade.tsx."""
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["analytics"])

_DIAS = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}


def _req_gestao(cu: User = Depends(get_current_user)) -> User:
    # Produtividade/ROI por advogado = dado gerencial sensível (auditoria 2026-06-30):
    # restrito a sócio+ (exclui estagiário/secretaria/financeiro/auxiliar).
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(status_code=403, detail="Acesso restrito à gestão")
    return cu


@router.get("/produtividade")
async def produtividade(
    periodo: str = Query("30d"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_gestao),
):
    dias = _DIAS.get(periodo, 30)
    desde = date.today() - timedelta(days=dias)

    # Por advogado
    adv = (await db.execute(text("""
        SELECT u.id, u.full_name AS nome,
               COALESCE(SUM(t.minutos),0)/60.0 AS horas,
               COALESCE(SUM(t.minutos) FILTER (WHERE t.faturavel),0)/60.0 AS horas_faturavel,
               COUNT(*) AS lancamentos,
               COUNT(DISTINCT t.case_id) AS casos
        FROM time_entries t JOIN users u ON u.id = t.user_id
        WHERE t.deleted_at IS NULL AND t.data >= :desde
        GROUP BY u.id, u.full_name ORDER BY horas DESC
    """), {"desde": desde})).mappings().all()
    por_advogado = []
    for a in adv:
        h = float(a["horas"]); hf = float(a["horas_faturavel"])
        por_advogado.append({
            "id": a["id"], "nome": a["nome"], "horas": round(h, 1),
            "horas_faturavel": round(hf, 1), "lancamentos": int(a["lancamentos"]),
            "casos": int(a["casos"]), "pct_faturavel": round(hf / h * 100) if h else 0,
        })

    # Por área (via caso)
    area = (await db.execute(text("""
        SELECT c.area,
               COALESCE(SUM(t.minutos),0)/60.0 AS horas,
               COALESCE(SUM(t.minutos) FILTER (WHERE t.faturavel),0)/60.0 AS horas_faturavel,
               COUNT(DISTINCT t.case_id) AS casos
        FROM time_entries t JOIN cases c ON c.id = t.case_id
        WHERE t.deleted_at IS NULL AND t.data >= :desde
        GROUP BY c.area ORDER BY horas DESC
    """), {"desde": desde})).mappings().all()
    por_area = [{
        "area": a["area"], "horas": round(float(a["horas"]), 1),
        "horas_faturavel": round(float(a["horas_faturavel"]), 1), "casos": int(a["casos"]),
    } for a in area]

    # Trend diário
    trend_rows = (await db.execute(text("""
        SELECT t.data::date AS dia, COALESCE(SUM(t.minutos),0)/60.0 AS horas
        FROM time_entries t WHERE t.deleted_at IS NULL AND t.data >= :desde
        GROUP BY t.data::date ORDER BY dia
    """), {"desde": desde})).mappings().all()
    trend = [{"dia": str(r["dia"]), "horas": round(float(r["horas"]), 1)} for r in trend_rows]

    total_h = sum(a["horas"] for a in por_advogado)
    total_hf = sum(a["horas_faturavel"] for a in por_advogado)
    total_lanc = sum(a["lancamentos"] for a in por_advogado)

    return {
        "periodo": periodo, "desde": str(desde),
        "resumo": {
            "total_horas": round(total_h, 1), "horas_faturavel": round(total_hf, 1),
            "pct_faturavel": round(total_hf / total_h * 100) if total_h else 0,
            "lancamentos": total_lanc,
        },
        "por_advogado": por_advogado, "por_area": por_area, "trend": trend,
    }


@router.get("/roi-por-area")
async def roi_por_area(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_gestao),
):
    """ROI por área jurídica — receita, custo e margem agrupados por ramo do direito."""
    from app.services.rentabilidade import ranking_por_area
    return await ranking_por_area(db, cu)
