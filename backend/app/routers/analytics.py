# ── app/routers/analytics.py ─────────────────────────────────────────────────
# Indicadores de gestão (Bloco D). Leitura analítica sobre dados existentes.
# Respeita o controle de acesso por advogado (mesmo critério do módulo de casos).
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles_exact
from app.models.user import User
from app.models.case import Case
from app.models.client import Client
from app.services import case_health
from app.services import jurimetria as jurimetria_svc
from app.services import taskscore as taskscore_svc
from app.services import funil as funil_svc
from app.services import rentabilidade as rent_svc
from app.services import onboarding as onb_svc

router = APIRouter(prefix="/analytics", tags=["analytics"])

_EQUIPE = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"]


@router.get("/jurimetria")
async def jurimetria_endpoint(
    dimensao: str | None = Query(None, description="area | comarca | advogado (vazio = global)"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Métricas de desfecho (taxa de êxito) com tamanho de amostra explícito.

    Considera apenas casos encerrados/arquivados com resultado registrado.
    """
    try:
        return await jurimetria_svc.jurimetria(db, cu, dimensao=dimensao)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/taskscore")
async def taskscore_endpoint(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Produtividade e carga por advogado (tarefas). Escopo conforme o perfil."""
    return await taskscore_svc.taskscore(db, cu)


@router.get("/funil")
async def funil_endpoint(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Funil de leads: estágios, conversão e quebra por canal de origem."""
    return await funil_svc.funil(db, cu)


@router.get("/rentabilidade")
async def rentabilidade_endpoint(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Rentabilidade por caso: receita recebida × custo de horas lançadas."""
    return await rent_svc.ranking_rentabilidade(db, cu, limit=limit)


@router.get("/onboarding")
async def onboarding_pendencias(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Clientes com onboarding incompleto (checklist de entrada). Escopo por perfil."""
    return await onb_svc.pendencias(db, cu, limit=limit)


@router.get("/onboarding/{client_id}")
async def onboarding_cliente(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Checklist de onboarding detalhado de um cliente."""
    client = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if not onb_svc.pode_ver_todos(cu) and client.responsavel_id != cu.id:
        raise HTTPException(status_code=403, detail="Sem acesso a este cliente")
    return await onb_svc.status_cliente(db, client)


@router.get("/case-health")
async def case_health_ranking(
    apenas_abertos: bool = Query(True, description="Considerar só casos em andamento"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Ranking de saúde dos casos (piores primeiro). Escopo conforme o perfil."""
    return await case_health.ranking_saude(db, cu, limit=limit, apenas_abertos=apenas_abertos)


@router.get("/case-health/{case_id}")
async def case_health_detalhe(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Score de saúde detalhado de um caso, com a memória de cada dedução."""
    case = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    # Controle de acesso: advogado só vê caso próprio
    if not case_health.pode_ver_todos(cu) and cu.id not in (
        case.advogado_responsavel_id, case.advogado_auxiliar_id
    ):
        raise HTTPException(status_code=403, detail="Sem acesso a este caso")
    return await case_health.calcular_score_caso(db, case)
