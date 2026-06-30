# ── app/routers/environmental.py ─────────────────────────────────────────────
# Módulo Ambiental: ao registrar ciência do auto de infração,
# calcula prazo de defesa (Decreto 6.514/08 art. 113) e cria
# AUTOMATICAMENTE uma deadline crítica vinculada ao caso.
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.case import Case
from app.models.deadline import Deadline, DeadlineTipo, DeadlinePrioridade
from app.models.environmental import EnvironmentalCase, StatusDefesa
from app.models.audit_log import criar_audit_log
from app.services.deadline_calculator import prazo_defesa_ambiental
from app.schemas.environmental import EnvCaseCreate, EnvCaseUpdate, EnvCaseResponse
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/environmental", tags=["Ambiental"])


async def _criar_deadline_defesa(
    db: AsyncSession, env: EnvironmentalCase, case: Case, user: User,
):
    """Cria deadline crítica para a defesa (data interna com margem)."""
    calc = prazo_defesa_ambiental(env.data_ciencia)
    env.data_prazo_defesa = calc["data_legal"]
    env.status_defesa = StatusDefesa.prazo_correndo

    d = Deadline(
        id=str(uuid4()),
        titulo=f"🌿 Defesa ambiental — Auto {env.numero_auto}",
        descricao=(
            f"Prazo LEGAL: {calc['data_legal'].strftime('%d/%m/%Y')} | "
            f"Meta interna: {calc['data_interna'].strftime('%d/%m/%Y')} "
            f"(margem de segurança)"
        ),
        tipo=DeadlineTipo.administrativo,
        prioridade=DeadlinePrioridade.critica,
        data_prazo=calc["data_interna"],   # meta interna = data segura
        data_intimacao=env.data_ciencia,
        base_legal=calc["base_legal"],
        case_id=case.id,
        responsavel_id=case.advogado_responsavel_id or user.id,
    )
    db.add(d)
    return calc


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    status_f: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(EnvironmentalCase).where(EnvironmentalCase.deleted_at.is_(None))
    if status_f:
        q = q.where(EnvironmentalCase.status_defesa == status_f)
    q = q.order_by(EnvironmentalCase.data_prazo_defesa.asc().nullslast())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [EnvCaseResponse.model_validate(e) for e in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/", response_model=EnvCaseResponse, status_code=201)
async def criar(
    payload: EnvCaseCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    case = (await db.execute(
        select(Case).where(
            Case.id == payload.case_id, Case.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=422, detail="Caso não encontrado")
    await verificar_acesso_caso(db, cu, case.id)

    # Unicidade: 1 env_case por caso
    exists = (await db.execute(
        select(EnvironmentalCase).where(
            EnvironmentalCase.case_id == payload.case_id,
            EnvironmentalCase.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(
            status_code=409, detail="Caso já possui registro ambiental"
        )

    env = EnvironmentalCase(id=str(uuid4()), **payload.model_dump())
    db.add(env)

    # Se já veio com data_ciencia: calcula prazo + cria deadline crítica
    info_prazo = None
    if env.data_ciencia:
        info_prazo = await _criar_deadline_defesa(db, env, case, cu)

    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "environmental_cases", env.id,
        detalhes=f"Auto {env.numero_auto} ({payload.orgao_autuador})",
    )
    await db.commit()
    await db.refresh(env)
    return env


@router.patch("/{env_id}", response_model=EnvCaseResponse)
async def atualizar(
    env_id: str, payload: EnvCaseUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    env = (await db.execute(
        select(EnvironmentalCase).where(
            EnvironmentalCase.id == env_id,
            EnvironmentalCase.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not env:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    if env.case_id:
        await verificar_acesso_caso(db, cu, env.case_id)

    mudancas = payload.model_dump(exclude_unset=True)
    ciencia_nova = (
        "data_ciencia" in mudancas
        and mudancas["data_ciencia"]
        and mudancas["data_ciencia"] != env.data_ciencia
    )
    for k, v in mudancas.items():
        setattr(env, k, v)

    # Ciência registrada agora → calcular prazo + deadline
    if ciencia_nova:
        case = (await db.execute(
            select(Case).where(Case.id == env.case_id)
        )).scalar_one()
        await _criar_deadline_defesa(db, env, case, cu)

    await criar_audit_log(
        db, cu.id, cu.role.value, "UPDATE", "environmental_cases", env_id,
    )
    await db.commit()
    await db.refresh(env)
    return env


@router.delete("/{env_id}", response_model=MsgResponse)
async def remover(
    env_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    env = (await db.execute(
        select(EnvironmentalCase).where(
            EnvironmentalCase.id == env_id,
            EnvironmentalCase.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not env:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    if env.case_id:
        await verificar_acesso_caso(db, cu, env.case_id)
    env.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db, cu.id, cu.role.value, "DELETE", "environmental_cases", env_id,
    )
    await db.commit()
    return MsgResponse(detail="Registro ambiental removido")
