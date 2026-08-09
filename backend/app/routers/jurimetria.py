# ── app/routers/jurimetria.py ──────────────────────────────────────────────────
# Jurimetria — métricas de desempenho por área, magistrado, tribunal e tese.
# Dados baseados em tese_caso_links (resultados registrados) + cases.
# Acesso: staff (advogado+); overview de alto nível: sócio+.
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case as sa_case
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import EQUIPE_JURIDICA, ROLE_LEVEL, get_current_user
from app.models.case import Case
from app.models.tese import Tese, TeseCasoLink, TeseStatus
from app.models.user import User

router = APIRouter(prefix="/jurimetria", tags=["Jurimetria"])


_RESULTADOS_DECIDIDOS = ("procedente", "improcedente")


def _is_staff(user: User) -> bool:
    # Issue #694: allowlist EXATA — financeiro não acessa métricas de
    # jurimetria, mesmo com ROLE_LEVEL acima de estagiario.
    return user.role.value in EQUIPE_JURIDICA


def _is_socio(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]


def _taxa_decidida(venceu: int, perdeu: int) -> float | None:
    """Taxa descritiva somente entre resultados decididos.

    `acordo` e `pendente` não entram no denominador: acordo não é vitória
    judicial e pendência não é desfecho. O total bruto continua exposto para
    transparência da amostra.
    """
    decididos = int(venceu or 0) + int(perdeu or 0)
    return round(int(venceu or 0) / decididos, 4) if decididos else None


@router.get("/overview")
async def overview(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Panorama dos vínculos de tese com denominador estatístico explícito."""
    if not _is_socio(cu):
        raise HTTPException(403, "Apenas sócios têm acesso ao painel de jurimetria")

    tot_row = (
        await db.execute(
            select(
                func.count(TeseCasoLink.id).label("total"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "procedente", 1))
                ).label("venceu"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "improcedente", 1))
                ).label("perdeu"),
                func.count(sa_case((TeseCasoLink.resultado == "acordo", 1))).label(
                    "acordo"
                ),
                func.count(sa_case((TeseCasoLink.resultado == "pendente", 1))).label(
                    "pendente"
                ),
            )
        )
    ).one()

    total = int(tot_row.total or 0)
    venceu = int(tot_row.venceu or 0)
    perdeu = int(tot_row.perdeu or 0)
    acordo = int(tot_row.acordo or 0)
    pendente = int(tot_row.pendente or 0)
    decididos = venceu + perdeu

    total_teses = (
        await db.execute(
            select(func.count(Tese.id)).where(
                Tese.deleted_at.is_(None), Tese.status == TeseStatus.ativa
            )
        )
    ).scalar() or 0

    total_casos = (
        await db.execute(select(func.count(Case.id)).where(Case.deleted_at.is_(None)))
    ).scalar() or 0

    return {
        "total_vinculos": total,
        "decididos": decididos,
        "venceu": venceu,
        "perdeu": perdeu,
        "acordo": acordo,
        "pendente": pendente,
        "taxa_sucesso_geral": _taxa_decidida(venceu, perdeu),
        "taxa_sucesso_denominador": "procedente + improcedente",
        "acordo_excluido_da_taxa": True,
        "pendente_excluido_da_taxa": True,
        "total_teses_ativas": total_teses,
        "total_casos": total_casos,
        "fonte": "base interna — vínculos de teses",
    }


@router.get("/por-area")
async def por_area(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Taxa de sucesso por área, calculada somente entre decisões."""
    if not _is_staff(cu):
        raise HTTPException(403)

    rows = (
        await db.execute(
            select(
                Tese.area_juridica,
                func.count(TeseCasoLink.id).label("total"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "procedente", 1))
                ).label("venceu"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "improcedente", 1))
                ).label("perdeu"),
                func.count(sa_case((TeseCasoLink.resultado == "acordo", 1))).label(
                    "acordo"
                ),
                func.count(sa_case((TeseCasoLink.resultado == "pendente", 1))).label(
                    "pendente"
                ),
            )
            .join(Tese, Tese.id == TeseCasoLink.tese_id)
            .where(Tese.deleted_at.is_(None))
            .group_by(Tese.area_juridica)
            .order_by(func.count(TeseCasoLink.id).desc())
            .limit(30)
        )
    ).all()

    resultado = []
    for r in rows:
        venceu = int(r.venceu or 0)
        perdeu = int(r.perdeu or 0)
        resultado.append(
            {
                "area": r.area_juridica or "Não classificada",
                "total": int(r.total or 0),
                "decididos": venceu + perdeu,
                "venceu": venceu,
                "perdeu": perdeu,
                "acordo": int(r.acordo or 0),
                "pendente": int(r.pendente or 0),
                "taxa_sucesso": _taxa_decidida(venceu, perdeu),
            }
        )
    return resultado


@router.get("/por-magistrado")
async def por_magistrado(
    area: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Desempenho por magistrado com amostra decidida explícita."""
    if not _is_staff(cu):
        raise HTTPException(403)

    q = (
        select(
            Tese.magistrado,
            func.count(TeseCasoLink.id).label("total"),
            func.count(
                sa_case((TeseCasoLink.resultado == "procedente", 1))
            ).label("venceu"),
            func.count(
                sa_case((TeseCasoLink.resultado == "improcedente", 1))
            ).label("perdeu"),
            func.count(sa_case((TeseCasoLink.resultado == "acordo", 1))).label(
                "acordo"
            ),
            func.count(sa_case((TeseCasoLink.resultado == "pendente", 1))).label(
                "pendente"
            ),
        )
        .join(Tese, Tese.id == TeseCasoLink.tese_id)
        .where(Tese.deleted_at.is_(None), Tese.magistrado.isnot(None))
    )
    if area:
        q = q.where(Tese.area_juridica.ilike(f"%{area}%"))

    q = (
        q.group_by(Tese.magistrado)
        .order_by(func.count(TeseCasoLink.id).desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()

    resultado = []
    for r in rows:
        venceu = int(r.venceu or 0)
        perdeu = int(r.perdeu or 0)
        resultado.append(
            {
                "magistrado": r.magistrado,
                "total": int(r.total or 0),
                "decididos": venceu + perdeu,
                "venceu": venceu,
                "perdeu": perdeu,
                "acordo": int(r.acordo or 0),
                "pendente": int(r.pendente or 0),
                "taxa_sucesso": _taxa_decidida(venceu, perdeu),
            }
        )
    return resultado


@router.get("/por-tribunal")
async def por_tribunal(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Desempenho agrupado por tribunal, com acordo fora da taxa judicial."""
    if not _is_staff(cu):
        raise HTTPException(403)

    rows = (
        await db.execute(
            select(
                Tese.tribunal,
                func.count(TeseCasoLink.id).label("total"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "procedente", 1))
                ).label("venceu"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "improcedente", 1))
                ).label("perdeu"),
                func.count(sa_case((TeseCasoLink.resultado == "acordo", 1))).label(
                    "acordo"
                ),
                func.count(sa_case((TeseCasoLink.resultado == "pendente", 1))).label(
                    "pendente"
                ),
            )
            .join(Tese, Tese.id == TeseCasoLink.tese_id)
            .where(Tese.deleted_at.is_(None), Tese.tribunal.isnot(None))
            .group_by(Tese.tribunal)
            .order_by(func.count(TeseCasoLink.id).desc())
            .limit(limit)
        )
    ).all()

    resultado = []
    for r in rows:
        venceu = int(r.venceu or 0)
        perdeu = int(r.perdeu or 0)
        resultado.append(
            {
                "tribunal": r.tribunal,
                "total": int(r.total or 0),
                "decididos": venceu + perdeu,
                "venceu": venceu,
                "perdeu": perdeu,
                "acordo": int(r.acordo or 0),
                "pendente": int(r.pendente or 0),
                "taxa_sucesso": _taxa_decidida(venceu, perdeu),
            }
        )
    return resultado


@router.get("/por-tese")
async def por_tese(
    area: Optional[str] = Query(None),
    min_usos: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Ranking legado de teses; taxa persistida no próprio cadastro da tese."""
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
            "id": t.id,
            "titulo": t.titulo,
            "area_juridica": t.area_juridica,
            "tribunal": t.tribunal,
            "vezes_usada": t.vezes_usada,
            "vezes_venceu": t.vezes_venceu,
            "vezes_perdeu": t.vezes_perdeu,
            "taxa_sucesso": t.taxa_sucesso,
            "fonte_metrica": "campo agregado da tese",
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

    rows = (
        await db.execute(
            text(
                """
                SELECT
                    TO_CHAR(DATE_TRUNC('month', created_at), 'YYYY-MM') AS mes,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE resultado = 'procedente') AS venceu,
                    COUNT(*) FILTER (WHERE resultado = 'improcedente') AS perdeu,
                    COUNT(*) FILTER (WHERE resultado = 'acordo') AS acordo,
                    COUNT(*) FILTER (WHERE resultado = 'pendente') AS pendente
                FROM tese_caso_links
                WHERE created_at >= NOW() - INTERVAL '12 months'
                GROUP BY DATE_TRUNC('month', created_at)
                ORDER BY DATE_TRUNC('month', created_at)
                """
            )
        )
    ).all()

    return [
        {
            "mes": r.mes,
            "total": int(r.total or 0),
            "decididos": int(r.venceu or 0) + int(r.perdeu or 0),
            "venceu": int(r.venceu or 0),
            "perdeu": int(r.perdeu or 0),
            "acordo": int(r.acordo or 0),
            "pendente": int(r.pendente or 0),
            "taxa": _taxa_decidida(r.venceu, r.perdeu),
        }
        for r in rows
    ]


@router.post("/predicao-exito", deprecated=True)
@router.post("/analise-prospectiva")
async def analise_prospectiva_qualitativa(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Análise prospectiva qualitativa por IA — não é modelo de probabilidade.

    O endpoint legado `/predicao-exito` permanece como alias para compatibilidade.
    A IA deve discutir fatores favoráveis/desfavoráveis, lacunas e riscos sem
    converter o texto em uma probabilidade numérica não calibrada.
    """
    from app.services.ai.core.orchestrator import orchestrator

    texto_contexto = payload.get("contexto")
    if not (texto_contexto or "").strip():
        raise HTTPException(422, "Envie o campo 'contexto' com a descrição do caso.")

    prompt = (
        "Produza uma análise prospectiva qualitativa deste caso. Separe fatores "
        "favoráveis, desfavoráveis, lacunas probatórias, riscos processuais e "
        "pontos que exigem confirmação. Não atribua probabilidade numérica de "
        "êxito sem modelo estatisticamente calibrado e amostra explicitamente "
        f"informada. Contexto: {texto_contexto}"
    )
    res = await orchestrator.run(
        db=db,
        user=cu,
        task_type="jurimetria",
        domain="jurimetria",
        mensagem=prompt,
        case_id=payload.get("case_id"),
    )
    return {
        "resultado": res.get("conteudo"),
        "tipo": "analise_prospectiva_qualitativa",
        "aviso": (
            "Análise qualitativa e preliminar; não representa probabilidade "
            "calibrada nem garantia de resultado. Requer validação do advogado."
        ),
        "is_estimativa": True,
        "modelo": res.get("modelo"),
        "provider": res.get("provider"),
        "log_id": res.get("log_id"),
        "is_rascunho": res.get("is_rascunho", True),
        "aviso_hitl": res.get("aviso_hitl"),
    }
