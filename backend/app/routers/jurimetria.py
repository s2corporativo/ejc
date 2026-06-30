# ── app/routers/jurimetria.py ──────────────────────────────────────────────────
# Jurimetria — métricas de desempenho por área, magistrado, tribunal e tese.
# Dados baseados em tese_caso_links (resultados registrados) + cases.
# Acesso: staff (advogado+); overview de alto nível: sócio+.
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, text, case as sa_case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.tese import Tese, TeseCasoLink, TeseStatus
from app.models.case import Case

router = APIRouter(prefix="/jurimetria", tags=["Jurimetria"])


def _is_staff(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["estagiario"]

def _is_socio(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]


@router.get("/overview")
async def overview(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Panorama geral: total de casos, vitórias, pendentes, taxa global de sucesso.
    """
    if not _is_socio(cu):
        raise HTTPException(403, "Apenas sócios têm acesso ao painel de jurimetria")

    # Total de vínculos com resultado registrado
    tot_row = (await db.execute(
        select(
            func.count(TeseCasoLink.id).label("total"),
            func.count(sa_case((TeseCasoLink.resultado == "procedente", 1))).label("venceu"),
            func.count(sa_case((TeseCasoLink.resultado == "improcedente", 1))).label("perdeu"),
            func.count(sa_case((TeseCasoLink.resultado == "acordo", 1))).label("acordo"),
            func.count(sa_case((TeseCasoLink.resultado == "pendente", 1))).label("pendente"),
        )
    )).one()

    total     = tot_row.total or 0
    venceu    = tot_row.venceu or 0
    perdeu    = tot_row.perdeu or 0
    taxa_global = round(venceu / total, 4) if total > 0 else None

    # Teses ativas
    total_teses = (await db.execute(
        select(func.count(Tese.id)).where(
            Tese.deleted_at.is_(None), Tese.status == TeseStatus.ativa
        )
    )).scalar() or 0

    # Casos ativos
    total_casos = (await db.execute(
        select(func.count(Case.id)).where(Case.deleted_at.is_(None))
    )).scalar() or 0

    return {
        "total_vinculos":    total,
        "venceu":            venceu,
        "perdeu":            perdeu,
        "acordo":            tot_row.acordo or 0,
        "pendente":          tot_row.pendente or 0,
        "taxa_sucesso_geral": taxa_global,
        "total_teses_ativas": total_teses,
        "total_casos":        total_casos,
    }


@router.get("/por-area")
async def por_area(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Taxa de sucesso agrupada por área jurídica."""
    if not _is_staff(cu):
        raise HTTPException(403)

    rows = (await db.execute(
        select(
            Tese.area_juridica,
            func.count(TeseCasoLink.id).label("total"),
            func.count(sa_case((TeseCasoLink.resultado == "procedente", 1))).label("venceu"),
            func.count(sa_case((TeseCasoLink.resultado == "improcedente", 1))).label("perdeu"),
        )
        .join(Tese, Tese.id == TeseCasoLink.tese_id)
        .where(Tese.deleted_at.is_(None))
        .group_by(Tese.area_juridica)
        .order_by(func.count(TeseCasoLink.id).desc())
        .limit(30)
    )).all()

    resultado = []
    for r in rows:
        total = r.total or 0
        venceu = r.venceu or 0
        resultado.append({
            "area": r.area_juridica or "Não classificada",
            "total":        total,
            "venceu":       venceu,
            "perdeu":       r.perdeu or 0,
            "taxa_sucesso": round(venceu / total, 4) if total > 0 else None,
        })
    return resultado


@router.get("/por-magistrado")
async def por_magistrado(
    area: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db:   AsyncSession = Depends(get_db),
    cu:   User = Depends(get_current_user),
):
    """Desempenho por magistrado (baseado nos vínculos de tese com magistrado registrado)."""
    if not _is_staff(cu):
        raise HTTPException(403)

    q = (
        select(
            Tese.magistrado,
            func.count(TeseCasoLink.id).label("total"),
            func.count(sa_case((TeseCasoLink.resultado == "procedente", 1))).label("venceu"),
            func.count(sa_case((TeseCasoLink.resultado == "improcedente", 1))).label("perdeu"),
        )
        .join(Tese, Tese.id == TeseCasoLink.tese_id)
        .where(Tese.deleted_at.is_(None), Tese.magistrado.isnot(None))
    )
    if area:
        q = q.where(Tese.area_juridica.ilike(f"%{area}%"))

    q = q.group_by(Tese.magistrado).order_by(func.count(TeseCasoLink.id).desc()).limit(limit)
    rows = (await db.execute(q)).all()

    resultado = []
    for r in rows:
        total = r.total or 0
        venceu = r.venceu or 0
        resultado.append({
            "magistrado":   r.magistrado,
            "total":        total,
            "venceu":       venceu,
            "perdeu":       r.perdeu or 0,
            "taxa_sucesso": round(venceu / total, 4) if total > 0 else None,
        })
    return resultado


@router.get("/por-tribunal")
async def por_tribunal(
    limit: int = Query(20, ge=1, le=50),
    db:    AsyncSession = Depends(get_db),
    cu:    User = Depends(get_current_user),
):
    """Desempenho agrupado por tribunal."""
    if not _is_staff(cu):
        raise HTTPException(403)

    rows = (await db.execute(
        select(
            Tese.tribunal,
            func.count(TeseCasoLink.id).label("total"),
            func.count(sa_case((TeseCasoLink.resultado == "procedente", 1))).label("venceu"),
            func.count(sa_case((TeseCasoLink.resultado == "improcedente", 1))).label("perdeu"),
        )
        .join(Tese, Tese.id == TeseCasoLink.tese_id)
        .where(Tese.deleted_at.is_(None), Tese.tribunal.isnot(None))
        .group_by(Tese.tribunal)
        .order_by(func.count(TeseCasoLink.id).desc())
        .limit(limit)
    )).all()

    resultado = []
    for r in rows:
        total = r.total or 0
        venceu = r.venceu or 0
        resultado.append({
            "tribunal":     r.tribunal,
            "total":        total,
            "venceu":       venceu,
            "perdeu":       r.perdeu or 0,
            "taxa_sucesso": round(venceu / total, 4) if total > 0 else None,
        })
    return resultado


@router.get("/por-tese")
async def por_tese(
    area:  Optional[str] = Query(None),
    min_usos: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db:    AsyncSession = Depends(get_db),
    cu:    User = Depends(get_current_user),
):
    """Ranking de teses por taxa de sucesso, com mínimo de usos configurável."""
    if not _is_staff(cu):
        raise HTTPException(403)

    q = select(Tese).where(
        Tese.deleted_at.is_(None),
        Tese.status == TeseStatus.ativa,
        Tese.vezes_usada >= min_usos,
    )
    if area:
        q = q.where(Tese.area_juridica.ilike(f"%{area}%"))
    q = q.order_by(Tese.taxa_sucesso.desc().nullslast()).limit(limit)

    teses = (await db.execute(q)).scalars().all()
    return [
        {
            "id":           t.id,
            "titulo":       t.titulo,
            "area_juridica": t.area_juridica,
            "tribunal":     t.tribunal,
            "vezes_usada":  t.vezes_usada,
            "vezes_venceu": t.vezes_venceu,
            "vezes_perdeu": t.vezes_perdeu,
            "taxa_sucesso": t.taxa_sucesso,
        }
        for t in teses
    ]


@router.get("/tendencias")
async def tendencias(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Vínculos de tese registrados por mês — últimos 12 meses."""
    if not _is_socio(cu):
        raise HTTPException(403)

    rows = (await db.execute(text("""
        SELECT
            TO_CHAR(DATE_TRUNC('month', created_at), 'YYYY-MM') AS mes,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE resultado = 'procedente')   AS venceu,
            COUNT(*) FILTER (WHERE resultado = 'improcedente') AS perdeu
        FROM tese_caso_links
        WHERE created_at >= NOW() - INTERVAL '12 months'
        GROUP BY DATE_TRUNC('month', created_at)
        ORDER BY DATE_TRUNC('month', created_at)
    """))).all()

    return [
        {
            "mes":    r.mes,
            "total":  r.total,
            "venceu": r.venceu,
            "perdeu": r.perdeu,
            "taxa":   round(r.venceu / r.total, 4) if r.total else None,
        }
        for r in rows
    ]


@router.post("/predicao-exito")
async def predicao_exito(payload: dict, cu: User = Depends(get_current_user)):
    """Jurimetria Preditiva: Cruzamento de dados para prever êxito."""
    from app.core.ai_brain import ai_brain
    texto = payload.get("contexto")
    prompt = f"Analise a probabilidade de êxito para este caso: {texto}"
    return {"predicao": await ai_brain.generate(prompt, "secundario")}

