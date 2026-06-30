# ── app/routers/tasks.py ─────────────────────────────────────────────────────
# Tarefas internas (kanban): delegação entre a equipe, por caso.
from __future__ import annotations
from datetime import datetime, timezone, date
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.task import Task, TaskStatus
from app.models.notification import Notification
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/tasks", tags=["Tarefas"])


class TaskIn(BaseModel):
    titulo: str
    descricao: Optional[str] = None
    prioridade: str = "media"
    data_limite: Optional[date] = None
    case_id: Optional[str] = None
    responsavel_id: Optional[str] = None


class TaskPatch(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    status: Optional[str] = None
    prioridade: Optional[str] = None
    data_limite: Optional[date] = None
    responsavel_id: Optional[str] = None


@router.get("/")
async def listar(
    case_id: Optional[str] = None,
    minhas: bool = Query(False, description="Só tarefas onde sou responsável"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Task).where(Task.deleted_at.is_(None))
    if case_id:
        q = q.where(Task.case_id == case_id)
    if minhas:
        q = q.where(Task.responsavel_id == cu.id)
    q = q.order_by(Task.data_limite.asc().nullslast(), Task.created_at)
    rows = (await db.execute(q)).scalars().all()
    return {"data": [
        {"id": t.id, "titulo": t.titulo, "descricao": t.descricao,
         "status": t.status.value, "prioridade": t.prioridade,
         "data_limite": t.data_limite, "case_id": t.case_id,
         "responsavel_id": t.responsavel_id, "created_at": t.created_at}
        for t in rows
    ]}


@router.post("/", status_code=201)
async def criar(
    payload: TaskIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    t = Task(id=str(uuid4()), criado_por=cu.id, **payload.model_dump())
    db.add(t)
    # Notificar o responsável (se não for o próprio criador)
    if payload.responsavel_id and payload.responsavel_id != cu.id:
        db.add(Notification(
            id=str(uuid4()), user_id=payload.responsavel_id,
            titulo="📋 Nova tarefa atribuída",
            mensagem=payload.titulo, tipo="tarefa", link="/tarefas",
        ))
    await db.commit()
    return {"id": t.id, "detail": "Tarefa criada"}


@router.patch("/{task_id}")
async def atualizar(
    task_id: str, payload: TaskPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    t = (await db.execute(select(Task).where(
        Task.id == task_id, Task.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    mud = payload.model_dump(exclude_unset=True)
    if "status" in mud:
        if mud["status"] not in [s.value for s in TaskStatus]:
            raise HTTPException(status_code=422, detail="Status inválido")
        if mud["status"] == "concluida" and t.status != TaskStatus.concluida:
            t.concluida_em = datetime.now(timezone.utc)
    for k, v in mud.items():
        setattr(t, k, v)
    await db.commit()
    return {"detail": "Tarefa atualizada"}


@router.delete("/{task_id}", response_model=MsgResponse)
async def remover(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    t = (await db.execute(select(Task).where(
        Task.id == task_id, Task.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    t.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return MsgResponse(detail="Tarefa removida")
