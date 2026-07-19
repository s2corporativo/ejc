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
from app.models.atendimento import Atendimento
from app.models.case import Case
from app.models.notification import Notification
from app.schemas.common import MsgResponse
from app.core.ownership import verificar_acesso_caso, is_gestao
from app.modules.auditoria.middleware import registrar_acao

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
    # IDOR (auditoria 2026-06-30): não-gestão só vê tarefas dos seus casos
    # (responsável/auxiliar), de casos sem dono, sem caso, ou onde é
    # responsável/criador. Espelha core.ownership.verificar_acesso_caso.
    if not is_gestao(cu):
        casos_visiveis = select(Case.id).where(
            Case.deleted_at.is_(None),
            (
                (Case.advogado_responsavel_id == cu.id)
                | (Case.advogado_auxiliar_id == cu.id)
                | (Case.advogado_responsavel_id.is_(None) & Case.advogado_auxiliar_id.is_(None))
            ),
        )
        q = q.where(
            Task.case_id.is_(None)
            | Task.case_id.in_(casos_visiveis)
            | (Task.responsavel_id == cu.id)
            | (Task.criado_por == cu.id)
        )
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
    if payload.case_id:
        await verificar_acesso_caso(db, cu, payload.case_id)
    # responsavel_id deve apontar p/ usuário REAL — espelha
    # agenda_eventos._validar_responsavel (evita tarefa/Notification órfã).
    if payload.responsavel_id:
        existe = (await db.execute(
            select(User.id).where(
                User.id == payload.responsavel_id, User.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if existe is None:
            raise HTTPException(
                status_code=422,
                detail="responsavel_id inválido: usuário não encontrado",
            )
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
    if t.case_id:
        await verificar_acesso_caso(db, cu, t.case_id)
    mud = payload.model_dump(exclude_unset=True)
    novo_status = None
    if "status" in mud:
        if mud["status"] not in [s.value for s in TaskStatus]:
            raise HTTPException(status_code=422, detail="Status inválido")
        novo_status = TaskStatus(mud.pop("status"))
        if novo_status == TaskStatus.concluida and t.status != TaskStatus.concluida:
            t.concluida_em = datetime.now(timezone.utc)
        elif novo_status != TaskStatus.concluida:
            t.concluida_em = None
        t.status = novo_status
    for k, v in mud.items():
        setattr(t, k, v)

    # Se a tarefa nasceu de uma solicitação de cliente, a conclusão (ou
    # reabertura) deve aparecer na mesma linha do tempo, sem dupla digitação.
    atendimento = (await db.execute(
        select(Atendimento).where(Atendimento.task_id == t.id)
    )).scalar_one_or_none()
    if atendimento is not None and novo_status is not None:
        concluida = novo_status == TaskStatus.concluida
        atendimento.solicitacao_atendida = concluida
        atendimento.atendida_em = t.concluida_em if concluida else None
        atendimento.atendida_por_id = cu.id if concluida else None
        atendimento.solicitacao_alerta_nivel = "concluido" if concluida else None
        atendimento.updated_at = datetime.now(timezone.utc)

    await db.commit()

    if atendimento is not None and novo_status is not None:
        role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
        await registrar_acao(
            db,
            cu.id,
            "atualizar",
            "atendimentos",
            atendimento.id,
            (
                "Solicitação sincronizada pela tarefa vinculada: "
                f"status {novo_status.value}"
            ),
            user_role=role,
            dados_depois={"solicitacao_atendida": atendimento.solicitacao_atendida},
        )
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
    if t.case_id:
        await verificar_acesso_caso(db, cu, t.case_id)
    t.deleted_at = datetime.now(timezone.utc)

    # Mantém a solicitação e seu histórico, mas remove a referência para uma
    # tarefa que deixou de existir operacionalmente.
    atendimento = (await db.execute(
        select(Atendimento).where(Atendimento.task_id == t.id)
    )).scalar_one_or_none()
    if atendimento is not None:
        atendimento.task_id = None
        atendimento.solicitacao_alerta_nivel = None
        atendimento.updated_at = datetime.now(timezone.utc)

    await db.commit()

    if atendimento is not None:
        role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
        await registrar_acao(
            db,
            cu.id,
            "atualizar",
            "atendimentos",
            atendimento.id,
            "Tarefa vinculada removida; solicitação mantida na linha do tempo",
            user_role=role,
            dados_depois={"tarefa_vinculada": False},
        )
    return MsgResponse(detail="Tarefa removida")
