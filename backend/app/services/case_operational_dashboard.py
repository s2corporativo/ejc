# ── app/services/case_operational_dashboard.py ───────────────────────────────
"""Pendências acionáveis do Dashboard, sempre limitadas ao escopo do usuário."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import case as sql_case
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import pode_ver_todos
from app.models.case import Case
from app.models.case_next_action import CaseNextAction, CaseNextActionWaiver
from app.models.deadline import Deadline, DeadlineStatus
from app.models.djen import DjenComunicacao
from app.models.legal_doc import LegalDoc, PecaStatus
from app.models.solicitacao_documento import SolicitacaoDocumento
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services.case_health import ABERTOS


async def _count(db: AsyncSession, query) -> int:
    return int((await db.execute(query)).scalar() or 0)


def _case_scope(user: User):
    query = select(Case.id).where(
        Case.deleted_at.is_(None),
        Case.status.in_(ABERTOS),
    )
    if not pode_ver_todos(user):
        query = query.where(
            or_(
                Case.advogado_responsavel_id == user.id,
                Case.advogado_auxiliar_id == user.id,
            )
        )
    return query


async def operational_pending_summary(
    db: AsyncSession,
    user: User,
) -> dict:
    """Contagens e destaques sem vazar casos fora do RBAC/ABAC."""
    now = datetime.now(timezone.utc)
    today = date.today()
    scope = _case_scope(user)

    no_owner = await _count(
        db,
        select(func.count()).select_from(Case).where(
            Case.id.in_(scope),
            Case.advogado_responsavel_id.is_(None),
        ),
    )

    has_action = exists(
        select(CaseNextAction.id).where(
            CaseNextAction.case_id == Case.id,
            CaseNextAction.completed_at.is_(None),
        )
    )
    has_waiver = exists(
        select(CaseNextActionWaiver.id).where(
            CaseNextActionWaiver.case_id == Case.id,
            CaseNextActionWaiver.revoked_at.is_(None),
            CaseNextActionWaiver.expires_at > now,
        )
    )
    no_next_action = await _count(
        db,
        select(func.count()).select_from(Case).where(
            Case.id.in_(scope),
            ~has_action,
            ~has_waiver,
        ),
    )

    overdue_next_actions = await _count(
        db,
        select(func.count()).select_from(CaseNextAction).where(
            CaseNextAction.case_id.in_(scope),
            CaseNextAction.completed_at.is_(None),
            CaseNextAction.due_at < now,
        ),
    )
    blocked_next_actions = await _count(
        db,
        select(func.count()).select_from(CaseNextAction).where(
            CaseNextAction.case_id.in_(scope),
            CaseNextAction.completed_at.is_(None),
            CaseNextAction.blocked.is_(True),
        ),
    )
    unconfirmed_deadlines = await _count(
        db,
        select(func.count()).select_from(Deadline).where(
            Deadline.case_id.in_(scope),
            Deadline.deleted_at.is_(None),
            Deadline.status == DeadlineStatus.pendente,
            or_(
                Deadline.confirmado.is_(False),
                Deadline.ciencia_confirmada.is_(False),
            ),
        ),
    )
    overdue_tasks = await _count(
        db,
        select(func.count()).select_from(Task).where(
            Task.case_id.in_(scope),
            Task.deleted_at.is_(None),
            Task.status != TaskStatus.concluida,
            Task.data_limite < today,
        ),
    )
    documents_waiting = await _count(
        db,
        select(func.count()).select_from(SolicitacaoDocumento).where(
            SolicitacaoDocumento.case_id.in_(scope),
            SolicitacaoDocumento.deleted_at.is_(None),
            SolicitacaoDocumento.status.in_(("pendente", "parcial")),
        ),
    )
    pieces_in_review = await _count(
        db,
        select(func.count()).select_from(LegalDoc).where(
            LegalDoc.case_id.in_(scope),
            LegalDoc.deleted_at.is_(None),
            LegalDoc.status.in_((PecaStatus.em_revisao, PecaStatus.corrigida)),
        ),
    )

    intimacoes_filter = DjenComunicacao.case_id.in_(scope)
    if not pode_ver_todos(user):
        intimacoes_filter = or_(
            DjenComunicacao.advogado_id == user.id,
            intimacoes_filter,
        )
    unprocessed_notices = await _count(
        db,
        select(func.count()).select_from(DjenComunicacao).where(
            DjenComunicacao.processada.is_(False),
            intimacoes_filter,
        ),
    )

    priority_order = sql_case(
        (CaseNextAction.due_at < now, 0),
        (CaseNextAction.urgency == "critica", 1),
        (CaseNextAction.blocked.is_(True), 2),
        (CaseNextAction.urgency == "alta", 3),
        else_=4,
    )
    highlight_row = (
        await db.execute(
            select(
                CaseNextAction.id,
                CaseNextAction.case_id,
                CaseNextAction.title,
                CaseNextAction.owner_id,
                CaseNextAction.due_at,
                CaseNextAction.urgency,
                CaseNextAction.blocked,
                CaseNextAction.blocked_reason,
                CaseNextAction.waiting_on,
                Case.numero_interno,
                Case.titulo.label("case_title"),
            )
            .join(Case, Case.id == CaseNextAction.case_id)
            .where(
                CaseNextAction.case_id.in_(scope),
                CaseNextAction.completed_at.is_(None),
            )
            .order_by(priority_order, CaseNextAction.due_at)
            .limit(1)
        )
    ).mappings().first()

    missing_rows = (
        await db.execute(
            select(
                Case.id,
                Case.numero_interno,
                Case.titulo,
                Case.advogado_responsavel_id,
            )
            .where(
                Case.id.in_(scope),
                ~has_action,
                ~has_waiver,
            )
            .order_by(Case.updated_at.asc())
            .limit(10)
        )
    ).mappings().all()

    highlight = None
    if highlight_row is not None:
        highlight = {
            **dict(highlight_row),
            "due_at": highlight_row["due_at"].isoformat(),
        }

    return {
        "escopo": "escritorio" if pode_ver_todos(user) else "meus_casos",
        "gerado_em": now.isoformat(),
        "contagens": {
            "casos_sem_responsavel": no_owner,
            "casos_sem_proxima_acao": no_next_action,
            "proximas_acoes_vencidas": overdue_next_actions,
            "proximas_acoes_bloqueadas": blocked_next_actions,
            "prazos_sem_conferencia": unconfirmed_deadlines,
            "intimacoes_nao_analisadas": unprocessed_notices,
            "tarefas_vencidas": overdue_tasks,
            "pecas_em_revisao": pieces_in_review,
            "documentos_aguardados": documents_waiting,
        },
        "destaque": highlight,
        "casos_sem_proxima_acao": [dict(row) for row in missing_rows],
        "indice_natureza": "operacional",
        "nao_representa_probabilidade_exito": True,
    }
