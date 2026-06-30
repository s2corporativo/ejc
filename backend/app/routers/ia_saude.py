"""
ia_saude.py — Dashboard de saúde da IA (#91). Somente Admin/Sócio.
Agrega o AILog (uso, custo, aproveitamento HITL, modelos) — só leitura, sem schema novo.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.ai_log import AILog

router = APIRouter(prefix="/ia-saude", tags=["IA — Saúde (Admin)"])


def _v(x):
    return x.value if hasattr(x, "value") else x


@router.get("/dashboard")
async def dashboard(
    dias: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    if role not in ("superadmin", "admin", "socio"):
        raise HTTPException(403, "Acesso restrito (admin/sócio)")

    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    w = AILog.created_at >= desde

    total = (await db.execute(
        select(sqlfunc.count()).select_from(AILog).where(w))).scalar() or 0
    custo = (await db.execute(
        select(sqlfunc.coalesce(sqlfunc.sum(AILog.custo_estimado), 0)).where(w))).scalar() or 0
    pii = (await db.execute(
        select(sqlfunc.count()).select_from(AILog).where(w, AILog.pii_removida.is_(True)))).scalar() or 0

    por_modelo = (await db.execute(
        select(AILog.modelo, sqlfunc.count()).where(w).group_by(AILog.modelo))).all()
    por_tipo = (await db.execute(
        select(AILog.tipo_uso, sqlfunc.count()).where(w).group_by(AILog.tipo_uso))).all()
    por_status = (await db.execute(
        select(AILog.status_hitl, sqlfunc.count()).where(w).group_by(AILog.status_hitl))).all()

    aplicados = sum(c for s, c in por_status if _v(s) == "aplicado")
    return {
        "periodo_dias": dias,
        "total_chamadas": total,
        "custo_total_brl": round(float(custo), 4),
        "taxa_aproveitamento_pct": round(aplicados / total * 100, 1) if total else None,
        "chamadas_com_pii_removida": pii,
        "por_modelo": {m: c for m, c in por_modelo},
        "por_tipo_uso": {_v(t): c for t, c in por_tipo},
        "por_status_hitl": {_v(s): c for s, c in por_status},
        "observacao": "Métricas de uso da IA (LGPD/OAB). Apenas leitura do AILog.",
    }
