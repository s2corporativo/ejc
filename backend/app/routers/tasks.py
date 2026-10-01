# ── app/routers/tasks.py ─────────────────────────────────────────────────────
# Tarefas internas (kanban): delegação entre a equipe, por caso.
from __future__ import annotations
from datetime import datetime, timezone, date
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
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
from app.core.pagination_cursor import CursorInvalido, make_cursor, parse_cursor
from app.modules.auditoria.middleware import registrar_acao

router = APIRouter(prefix="/tasks", tags=["Tarefas"])

# Ordenação canônica do modo cursor (Tarefa 2 — baseline §10): chave estável
# com desempate ABSOLUTO (id). O legacy ordena por (data_limite NULLS LAST,
# created_at) — sem id, linhas com created_at idêntico podem pular/duplicar
# entre chamadas; o modo cursor fecha esse buraco sem tocar o legado.
_CURSOR_ORDER = "data_limite.asc.nullslast|created_at.asc|id.asc"


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


def _ids_casos_do_usuario(cu: User):
    return (
        select(Case.id)
        .where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            ),
        )
        .scalar_subquery()
    )


async def _carregar_responsavel_ativo(db: AsyncSession, responsavel_id: str) -> User:
    alvo = (
        await db.execute(
            select(User).where(
                User.id == responsavel_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if alvo is None:
        raise HTTPException(
            status_code=422,
            detail="responsavel_id inválido: usuário ativo não encontrado",
        )
    if getattr(alvo.role, "value", alvo.role) == "cliente_externo":
        raise HTTPException(
            status_code=422,
            detail="responsavel_id inválido: tarefas internas não podem ser atribuídas a cliente externo",
        )
    return alvo


def _responsavel_pode_acessar_caso(alvo: User, caso: Case) -> bool:
    return bool(
        is_gestao(alvo)
        or alvo.id in (caso.advogado_responsavel_id, caso.advogado_auxiliar_id)
    )


async def _verificar_acesso_tarefa(
    db: AsyncSession,
    cu: User,
    tarefa: Task,
) -> Case | None:
    """Gate único: com caso segue ownership do caso; sem caso é pessoal."""
    if tarefa.case_id:
        return await verificar_acesso_caso(db, cu, tarefa.case_id)
    if is_gestao(cu) or cu.id in (tarefa.responsavel_id, tarefa.criado_por):
        return None
    raise HTTPException(status_code=403, detail="Sem permissão para esta tarefa")


def _keyset_continuacao(q, last: list):
    """Continua DEPOIS de last=(data_limite, created_at, id) sob NULLS LAST.

    Comparador de tupla do Postgres não serve: NULL não compara (a linha com
    data_limite NULL sairia da página). RAMOS explícitos com os impossíveis
    eliminados em Python — NULLS LAST em ASC significa NULL ≡ +infinito:
    após um last com valor, NULLs ainda estão à frente; após um last NULL,
    só restam NULLs ordenadas por (created_at, id).
    """
    last_dl, last_ca, last_id = last
    if last_dl is None:
        return q.where(
            Task.data_limite.is_(None),
            or_(
                Task.created_at > last_ca,
                and_(Task.created_at == last_ca, Task.id > last_id),
            ),
        )
    return q.where(
        or_(
            Task.data_limite.is_(None),  # NULLS LAST: vem depois de qualquer valor
            Task.data_limite > last_dl,
            and_(
                Task.data_limite == last_dl,
                or_(
                    Task.created_at > last_ca,
                    and_(Task.created_at == last_ca, Task.id > last_id),
                ),
            ),
        )
    )


@router.get("/")
async def listar(
    case_id: Optional[str] = None,
    minhas: bool = Query(False, description="Só tarefas onde sou responsável"),
    # Opt-in de performance (Tarefa 2; baseline §10): `pagination=cursor`
    # troca o feed completo por páginas keyset assinadas (HMAC, revalidadas
    # por usuário/filtros/ordem). Default preserva o contrato atual (sem
    # corte) — nenhum cliente quebra; rollback = parar de enviar o parâmetro.
    pagination: str = Query("offset", pattern="^(offset|cursor)$"),
    cursor: Optional[str] = None,
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Task).where(Task.deleted_at.is_(None))
    if case_id:
        q = q.where(Task.case_id == case_id)
    if minhas:
        q = q.where(Task.responsavel_id == cu.id)

    # Regra canônica: tarefa COM caso só é visível pela carteira do caso;
    # tarefa SEM caso é pessoal ao criador/responsável. Casos órfãos não são
    # escape-hatch para perfis baixos — somente gestão pode vê-los.
    if not is_gestao(cu):
        q = q.where(
            or_(
                Task.case_id.in_(_ids_casos_do_usuario(cu)),
                and_(
                    Task.case_id.is_(None),
                    or_(
                        Task.responsavel_id == cu.id,
                        Task.criado_por == cu.id,
                    ),
                ),
            )
        )
    filtros = {"case_id": case_id, "minhas": minhas}

    if pagination == "cursor":
        # ── Modo keyset (opt-in) ─────────────────────────────────────────
        # O predicado de visibilidade acima é reavaliado NESTA query — a
        # página nunca é concedida pelo cursor, sempre pela carteira atual.
        last: list | None = None
        if cursor:
            try:
                last = parse_cursor(cursor, "tasks", cu, filtros, _CURSOR_ORDER)
            except CursorInvalido as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            if len(last) != 3:
                raise HTTPException(
                    status_code=409,
                    detail="cursor incompatível com a ordenação atual",
                )
            # Coerção de tipos: o cursor serializa ISO; a comparação SQL
            # exige date/datetime nativos (asyncpg não compara colunas com
            # texto cru). Formato ruim aqui = cursor de outro contrato → 409.
            try:
                last = [
                    date.fromisoformat(last[0]) if last[0] else None,
                    datetime.fromisoformat(last[1]),
                    str(last[2]),
                ]
            except (ValueError, TypeError) as exc:
                raise HTTPException(
                    status_code=409,
                    detail="cursor com chave de continuação inválida",
                ) from exc
        q = q.order_by(
            Task.data_limite.asc().nullslast(), Task.created_at.asc(), Task.id.asc()
        )
        if last is not None:
            q = _keyset_continuacao(q, last)
        # page_size+1 resolve has_more sem count(*) (o custo que se quer eliminar).
        rows = (await db.execute(q.limit(page_size + 1))).scalars().all()
        tem_mais = len(rows) > page_size
        rows = rows[:page_size]
        next_cursor = None
        if tem_mais and rows:
            ultimo = rows[-1]
            next_cursor = make_cursor(
                "tasks", cu, filtros, _CURSOR_ORDER,
                [
                    ultimo.data_limite.isoformat() if ultimo.data_limite else None,
                    ultimo.created_at.isoformat() if ultimo.created_at else None,
                    ultimo.id,
                ],
            )
        return {
            "data": [
                {"id": t.id, "titulo": t.titulo, "descricao": t.descricao,
                 "status": t.status.value, "prioridade": t.prioridade,
                 "data_limite": t.data_limite, "case_id": t.case_id,
                 "responsavel_id": t.responsavel_id, "created_at": t.created_at,
                 "concluida_em": t.concluida_em}
                for t in rows
            ],
            "page_size": page_size,
            "has_more": tem_mais,
            "next_cursor": next_cursor,
        }

    # ── Legado (inalterado): feed completo, sem corte ────────────────────
    q = q.order_by(Task.data_limite.asc().nullslast(), Task.created_at)
    rows = (await db.execute(q)).scalars().all()
    return {"data": [
        {"id": t.id, "titulo": t.titulo, "descricao": t.descricao,
         "status": t.status.value, "prioridade": t.prioridade,
         "data_limite": t.data_limite, "case_id": t.case_id,
         "responsavel_id": t.responsavel_id, "created_at": t.created_at,
         "concluida_em": t.concluida_em}
        for t in rows
    ]}


@router.post("/", status_code=201)
async def criar(
    payload: TaskIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    caso = None
    if payload.case_id:
        caso = await verificar_acesso_caso(db, cu, payload.case_id)

    alvo = None
    if payload.responsavel_id is not None:
        alvo = await _carregar_responsavel_ativo(db, payload.responsavel_id)
        if caso is not None and not _responsavel_pode_acessar_caso(alvo, caso):
            raise HTTPException(
                status_code=422,
                detail=(
                    "responsavel_id sem acesso ao caso: atribua a gestão, "
                    "responsável ou auxiliar do próprio caso"
                ),
            )

    t = Task(id=str(uuid4()), criado_por=cu.id, **payload.model_dump())
    db.add(t)
    # Notificar o responsável (se não for o próprio criador). A validação acima
    # impede enviar metadados de caso a usuário que não tenha acesso a ele.
    if alvo is not None and alvo.id != cu.id:
        db.add(Notification(
            id=str(uuid4()), user_id=alvo.id,
            titulo="📋 Nova tarefa atribuída",
            mensagem=payload.titulo, tipo="tarefa", link="/atividades?tipo=tarefa",
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
    caso = await _verificar_acesso_tarefa(db, cu, t)

    mud = payload.model_dump(exclude_unset=True)
    if "responsavel_id" in mud and mud["responsavel_id"] is not None:
        alvo = await _carregar_responsavel_ativo(db, mud["responsavel_id"])
        if caso is not None and not _responsavel_pode_acessar_caso(alvo, caso):
            raise HTTPException(
                status_code=422,
                detail=(
                    "responsavel_id sem acesso ao caso: atribua a gestão, "
                    "responsável ou auxiliar do próprio caso"
                ),
            )

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
    await _verificar_acesso_tarefa(db, cu, t)
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