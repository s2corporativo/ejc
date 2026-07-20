"""Consulta dados do caso e aplica as regras puras de saúde operacional."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.atendimento import Atendimento
from app.models.case import Case, CaseMovimento
from app.models.deadline import Deadline, DeadlineStatus
from app.models.document import Document
from app.models.legal_doc import LegalDoc, PecaStatus
from app.models.process import Process
from app.models.task import Task, TaskStatus
from app.services.case_activity_utils import as_utc_datetime, enum_value
from app.services.case_health_rules import assess_operational_health


async def operational_health(
    db: AsyncSession,
    case_id: str,
    *,
    stale_days: int = 30,
) -> dict[str, Any]:
    case = (
        await db.execute(
            select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if case is None:
        return {"found": False, "case_id": case_id}

    now = datetime.now(timezone.utc)
    today = now.date()

    # As mesmas fontes e os mesmos fallbacks são usados pela visão agregada da
    # carteira. Isso garante paridade de inatividade e score entre Dashboard e
    # diagnóstico individual, inclusive para registros históricos sem updated_at.
    last_values = [
        case.updated_at or case.created_at,
        await db.scalar(
            select(
                func.max(
                    func.coalesce(
                        CaseMovimento.data_evento,
                        CaseMovimento.created_at,
                    )
                )
            ).where(CaseMovimento.case_id == case_id)
        ),
        await db.scalar(
            select(func.max(func.coalesce(Document.updated_at, Document.created_at))).where(
                Document.case_id == case_id,
                Document.deleted_at.is_(None),
            )
        ),
        await db.scalar(
            select(func.max(Atendimento.data_atendimento)).where(
                Atendimento.case_id == case_id
            )
        ),
        await db.scalar(
            select(func.max(func.coalesce(Task.updated_at, Task.created_at))).where(
                Task.case_id == case_id,
                Task.deleted_at.is_(None),
            )
        ),
        await db.scalar(
            select(func.max(func.coalesce(Process.updated_at, Process.created_at))).where(
                Process.case_id == case_id,
                Process.deleted_at.is_(None),
            )
        ),
        await db.scalar(
            select(
                func.max(func.coalesce(LegalDoc.updated_at, LegalDoc.created_at))
            ).where(
                LegalDoc.case_id == case_id,
                LegalDoc.deleted_at.is_(None),
            )
        ),
    ]
    candidates = [as_utc_datetime(value) for value in last_values if value is not None]
    last_activity = (
        max(candidates) if candidates else as_utc_datetime(case.created_at)
    )
    inactive_days = max(0, (now - last_activity).days)

    metrics = {
        "active_processes": int(
            await db.scalar(
                select(func.count(Process.id)).where(
                    Process.case_id == case_id,
                    Process.deleted_at.is_(None),
                    Process.status != "arquivado",
                )
            )
            or 0
        ),
        "actionable_tasks": int(
            await db.scalar(
                select(func.count(Task.id)).where(
                    Task.case_id == case_id,
                    Task.deleted_at.is_(None),
                    Task.status.in_([TaskStatus.a_fazer, TaskStatus.fazendo]),
                )
            )
            or 0
        ),
        "overdue_deadlines": int(
            await db.scalar(
                select(func.count(Deadline.id)).where(
                    Deadline.case_id == case_id,
                    Deadline.deleted_at.is_(None),
                    Deadline.status.notin_(
                        [DeadlineStatus.concluido, DeadlineStatus.cancelado]
                    ),
                    Deadline.data_prazo < today,
                )
            )
            or 0
        ),
        "deadlines_next_3_days": int(
            await db.scalar(
                select(func.count(Deadline.id)).where(
                    Deadline.case_id == case_id,
                    Deadline.deleted_at.is_(None),
                    Deadline.status.notin_(
                        [DeadlineStatus.concluido, DeadlineStatus.cancelado]
                    ),
                    Deadline.data_prazo >= today,
                    Deadline.data_prazo <= today + timedelta(days=3),
                )
            )
            or 0
        ),
        "overdue_client_requests": int(
            await db.scalar(
                select(func.count(Atendimento.id)).where(
                    Atendimento.case_id == case_id,
                    Atendimento.solicitacao_atendida.is_(False),
                    Atendimento.solicitacao_prazo.is_not(None),
                    Atendimento.solicitacao_prazo < now,
                )
            )
            or 0
        ),
        "unreviewed_ai_documents": int(
            await db.scalar(
                select(func.count(LegalDoc.id)).where(
                    LegalDoc.case_id == case_id,
                    LegalDoc.deleted_at.is_(None),
                    LegalDoc.ai_generated.is_(True),
                    LegalDoc.human_reviewed.is_(False),
                )
            )
            or 0
        ),
        "documents_in_review": int(
            await db.scalar(
                select(func.count(LegalDoc.id)).where(
                    LegalDoc.case_id == case_id,
                    LegalDoc.deleted_at.is_(None),
                    LegalDoc.status.in_([PecaStatus.rascunho, PecaStatus.em_revisao]),
                )
            )
            or 0
        ),
    }
    assessment = assess_operational_health(
        case_status=str(enum_value(case.status)),
        has_judicial_process=bool(case.has_judicial_process),
        inactive_days=inactive_days,
        stale_days=stale_days,
        metrics=metrics,
    )
    return {
        "found": True,
        "case_id": case_id,
        **assessment,
        "last_activity_at": last_activity.isoformat(),
        "inactive_days": inactive_days,
        "stale_threshold_days": stale_days,
        "metrics": metrics,
    }
