"""Linha do tempo única e diagnóstico operacional do caso."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
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


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _datetime(value: datetime | date | None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _event(
    *,
    event_id: str,
    kind: str,
    title: str,
    occurred_at: datetime | date | None,
    description: str | None = None,
    status: str | None = None,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dt = _datetime(occurred_at)
    return {
        "id": f"{source}:{event_id}",
        "entity_id": event_id,
        "kind": kind,
        "title": title,
        "description": description,
        "status": status,
        "source": source,
        "occurred_at": dt.isoformat(),
        "metadata": metadata or {},
        "_sort_at": dt,
    }


async def timeline(
    db: AsyncSession,
    case_id: str,
    *,
    page: int = 1,
    per_page: int = 50,
    source_limit: int = 500,
) -> dict[str, Any]:
    """Normaliza eventos dos domínios sem duplicar a persistência de origem."""
    events: list[dict[str, Any]] = []
    saturated_sources: list[str] = []

    movements = (
        await db.execute(
            select(CaseMovimento)
            .where(CaseMovimento.case_id == case_id)
            .order_by(CaseMovimento.data_evento.desc(), CaseMovimento.created_at.desc())
            .limit(source_limit)
        )
    ).scalars().all()
    if len(movements) == source_limit:
        saturated_sources.append("case_movimentos")
    events.extend(
        _event(
            event_id=row.id,
            kind="movement",
            title=f"Movimentação: {_value(row.tipo)}",
            description=row.descricao,
            occurred_at=row.data_evento or row.created_at,
            status=None,
            source="case_movimentos",
            metadata={"resumo_ia": row.resumo_ia},
        )
        for row in movements
    )

    processes = (
        await db.execute(
            select(Process)
            .where(Process.case_id == case_id, Process.deleted_at.is_(None))
            .order_by(Process.created_at.desc())
            .limit(source_limit)
        )
    ).scalars().all()
    if len(processes) == source_limit:
        saturated_sources.append("processes")
    events.extend(
        _event(
            event_id=row.id,
            kind="process",
            title=("Processo principal" if row.is_principal else "Processo vinculado"),
            description=row.numero_cnj or "Processo sem numeração informada",
            occurred_at=row.created_at,
            status=row.status,
            source="processes",
            metadata={
                "numero_cnj": row.numero_cnj,
                "tipo": row.tipo,
                "tribunal": row.tribunal,
                "is_principal": bool(row.is_principal),
            },
        )
        for row in processes
    )

    documents = (
        await db.execute(
            select(Document)
            .where(Document.case_id == case_id, Document.deleted_at.is_(None))
            .order_by(Document.created_at.desc())
            .limit(source_limit)
        )
    ).scalars().all()
    if len(documents) == source_limit:
        saturated_sources.append("documents")
    events.extend(
        _event(
            event_id=row.id,
            kind="document",
            title=row.titulo,
            description=row.nome_arquivo,
            occurred_at=row.created_at,
            status=None,
            source="documents",
            metadata={
                "tipo": _value(row.tipo),
                "confidencialidade": _value(row.confidencialidade),
            },
        )
        for row in documents
    )

    deadlines = (
        await db.execute(
            select(Deadline)
            .where(Deadline.case_id == case_id, Deadline.deleted_at.is_(None))
            .order_by(Deadline.data_prazo.desc())
            .limit(source_limit)
        )
    ).scalars().all()
    if len(deadlines) == source_limit:
        saturated_sources.append("deadlines")
    events.extend(
        _event(
            event_id=row.id,
            kind="deadline",
            title=row.titulo,
            description=row.descricao,
            occurred_at=row.data_prazo,
            status=_value(row.status),
            source="deadlines",
            metadata={
                "tipo": _value(row.tipo),
                "prioridade": _value(row.prioridade),
                "confirmado": bool(row.confirmado),
                "origem": row.origem,
            },
        )
        for row in deadlines
    )

    tasks = (
        await db.execute(
            select(Task)
            .where(Task.case_id == case_id, Task.deleted_at.is_(None))
            .order_by(Task.created_at.desc())
            .limit(source_limit)
        )
    ).scalars().all()
    if len(tasks) == source_limit:
        saturated_sources.append("tasks")
    events.extend(
        _event(
            event_id=row.id,
            kind="task",
            title=row.titulo,
            description=row.descricao,
            occurred_at=row.concluida_em or row.created_at,
            status=_value(row.status),
            source="tasks",
            metadata={
                "prioridade": row.prioridade,
                "data_limite": row.data_limite.isoformat() if row.data_limite else None,
                "responsavel_id": row.responsavel_id,
            },
        )
        for row in tasks
    )

    attendances = (
        await db.execute(
            select(Atendimento)
            .where(Atendimento.case_id == case_id)
            .order_by(Atendimento.data_atendimento.desc())
            .limit(source_limit)
        )
    ).scalars().all()
    if len(attendances) == source_limit:
        saturated_sources.append("atendimentos")
    events.extend(
        _event(
            event_id=row.id,
            kind="attendance",
            title=f"Atendimento: {_value(row.tipo)}",
            description=row.resumo,
            occurred_at=row.data_atendimento,
            status=("atendida" if row.solicitacao_atendida else "pendente"),
            source="atendimentos",
            metadata={
                "solicitacao": row.solicitacao,
                "proximo_passo": row.proximo_passo,
                "prazo_retorno": (
                    row.solicitacao_prazo.isoformat() if row.solicitacao_prazo else None
                ),
                "contato_status": row.contato_status,
            },
        )
        for row in attendances
    )

    legal_docs = (
        await db.execute(
            select(LegalDoc)
            .where(LegalDoc.case_id == case_id, LegalDoc.deleted_at.is_(None))
            .order_by(LegalDoc.created_at.desc())
            .limit(source_limit)
        )
    ).scalars().all()
    if len(legal_docs) == source_limit:
        saturated_sources.append("legal_docs")
    events.extend(
        _event(
            event_id=row.id,
            kind="legal_document",
            title=row.titulo,
            description=f"Versão {row.versao}",
            occurred_at=row.protocolado_em or row.revisado_em or row.created_at,
            status=_value(row.status),
            source="legal_docs",
            metadata={
                "tipo_peca": _value(row.tipo_peca),
                "codigo_peca": row.codigo_peca,
                "ai_generated": bool(row.ai_generated),
                "human_reviewed": bool(row.human_reviewed),
                "numero_protocolo": row.numero_protocolo,
            },
        )
        for row in legal_docs
    )

    events.sort(key=lambda item: item["_sort_at"], reverse=True)
    for item in events:
        item.pop("_sort_at", None)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "case_id": case_id,
        "page": page,
        "per_page": per_page,
        "total_loaded": len(events),
        "truncated": bool(saturated_sources),
        "saturated_sources": sorted(saturated_sources),
        "items": events[start:end],
    }


def _indicator(
    code: str,
    severity: str,
    message: str,
    action: str,
    *,
    count: int | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
        "recommended_action": action,
    }
    if count is not None:
        item["count"] = count
    return item


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

    last_movement = await db.scalar(
        select(func.max(CaseMovimento.data_evento)).where(CaseMovimento.case_id == case_id)
    )
    last_document = await db.scalar(
        select(func.max(Document.created_at)).where(
            Document.case_id == case_id,
            Document.deleted_at.is_(None),
        )
    )
    last_attendance = await db.scalar(
        select(func.max(Atendimento.data_atendimento)).where(Atendimento.case_id == case_id)
    )
    last_task = await db.scalar(
        select(func.max(Task.updated_at)).where(
            Task.case_id == case_id,
            Task.deleted_at.is_(None),
        )
    )
    activity_candidates = [
        _datetime(value)
        for value in [case.updated_at, last_movement, last_document, last_attendance, last_task]
        if value is not None
    ]
    last_activity = max(activity_candidates) if activity_candidates else _datetime(case.created_at)
    inactive_days = max(0, (now - last_activity).days)

    active_processes = int(
        await db.scalar(
            select(func.count(Process.id)).where(
                Process.case_id == case_id,
                Process.deleted_at.is_(None),
                Process.status != "arquivado",
            )
        )
        or 0
    )
    pending_tasks = int(
        await db.scalar(
            select(func.count(Task.id)).where(
                Task.case_id == case_id,
                Task.deleted_at.is_(None),
                Task.status != TaskStatus.concluida,
            )
        )
        or 0
    )
    overdue_deadlines = int(
        await db.scalar(
            select(func.count(Deadline.id)).where(
                Deadline.case_id == case_id,
                Deadline.deleted_at.is_(None),
                Deadline.status.notin_([DeadlineStatus.concluido, DeadlineStatus.cancelado]),
                Deadline.data_prazo < today,
            )
        )
        or 0
    )
    critical_deadlines = int(
        await db.scalar(
            select(func.count(Deadline.id)).where(
                Deadline.case_id == case_id,
                Deadline.deleted_at.is_(None),
                Deadline.status.notin_([DeadlineStatus.concluido, DeadlineStatus.cancelado]),
                Deadline.data_prazo >= today,
                Deadline.data_prazo <= date.fromordinal(today.toordinal() + 3),
            )
        )
        or 0
    )
    overdue_requests = int(
        await db.scalar(
            select(func.count(Atendimento.id)).where(
                Atendimento.case_id == case_id,
                Atendimento.solicitacao_atendida.is_(False),
                Atendimento.solicitacao_prazo.is_not(None),
                Atendimento.solicitacao_prazo < now,
            )
        )
        or 0
    )
    unreviewed_ai_docs = int(
        await db.scalar(
            select(func.count(LegalDoc.id)).where(
                LegalDoc.case_id == case_id,
                LegalDoc.deleted_at.is_(None),
                LegalDoc.ai_generated.is_(True),
                LegalDoc.human_reviewed.is_(False),
            )
        )
        or 0
    )
    docs_in_review = int(
        await db.scalar(
            select(func.count(LegalDoc.id)).where(
                LegalDoc.case_id == case_id,
                LegalDoc.deleted_at.is_(None),
                LegalDoc.status.in_([PecaStatus.rascunho, PecaStatus.em_revisao]),
            )
        )
        or 0
    )

    indicators: list[dict[str, Any]] = []
    score = 100
    case_status = _value(case.status)
    active_case = case_status not in {"encerrado", "arquivado"}

    if overdue_deadlines:
        indicators.append(
            _indicator(
                "OVERDUE_DEADLINES",
                "critical",
                "Há prazos vencidos sem conclusão ou cancelamento.",
                "Abrir a Central de Agenda e Prazos e regularizar imediatamente.",
                count=overdue_deadlines,
            )
        )
        score -= min(45, 20 + overdue_deadlines * 5)
    if critical_deadlines:
        indicators.append(
            _indicator(
                "DEADLINES_NEXT_3_DAYS",
                "high",
                "Há prazos com vencimento nos próximos três dias.",
                "Confirmar ciência, responsável e tarefa vinculada.",
                count=critical_deadlines,
            )
        )
        score -= min(20, 5 + critical_deadlines * 3)
    if active_case and inactive_days > stale_days:
        indicators.append(
            _indicator(
                "CASE_INACTIVE",
                "high",
                f"Caso sem atividade relevante há {inactive_days} dias.",
                "Registrar revisão estratégica e definir o próximo passo.",
            )
        )
        score -= 20
    if active_case and pending_tasks == 0:
        indicators.append(
            _indicator(
                "NO_PENDING_TASK",
                "medium",
                "Caso ativo sem tarefa pendente.",
                "Criar a próxima ação com responsável e data limite.",
            )
        )
        score -= 10
    if case.has_judicial_process and active_processes == 0:
        indicators.append(
            _indicator(
                "MISSING_ACTIVE_PROCESS",
                "high",
                "Caso marcado como judicial sem processo ativo na entidade canônica.",
                "Cadastrar ou desarquivar o processo principal.",
            )
        )
        score -= 20
    if overdue_requests:
        indicators.append(
            _indicator(
                "CLIENT_REQUEST_OVERDUE",
                "high",
                "Solicitações de cliente ultrapassaram o prazo de retorno.",
                "Responder o cliente e concluir ou reprogramar a solicitação.",
                count=overdue_requests,
            )
        )
        score -= min(20, 8 + overdue_requests * 3)
    if unreviewed_ai_docs:
        indicators.append(
            _indicator(
                "AI_DOCUMENTS_UNREVIEWED",
                "medium",
                "Há documentos gerados por IA sem revisão humana registrada.",
                "Revisar, corrigir e aprovar antes de uso externo ou protocolo.",
                count=unreviewed_ai_docs,
            )
        )
        score -= min(15, 5 + unreviewed_ai_docs * 2)
    if docs_in_review:
        indicators.append(
            _indicator(
                "DOCUMENTS_IN_REVIEW",
                "low",
                "Há peças em rascunho ou revisão.",
                "Conferir a fila de produção e os responsáveis.",
                count=docs_in_review,
            )
        )
        score -= min(8, docs_in_review)

    score = max(0, score)
    if score >= 85:
        level = "healthy"
    elif score >= 65:
        level = "attention"
    elif score >= 40:
        level = "risk"
    else:
        level = "critical"

    return {
        "found": True,
        "case_id": case_id,
        "score": score,
        "level": level,
        "last_activity_at": last_activity.isoformat(),
        "inactive_days": inactive_days,
        "stale_threshold_days": stale_days,
        "metrics": {
            "active_processes": active_processes,
            "pending_tasks": pending_tasks,
            "overdue_deadlines": overdue_deadlines,
            "deadlines_next_3_days": critical_deadlines,
            "overdue_client_requests": overdue_requests,
            "unreviewed_ai_documents": unreviewed_ai_docs,
            "documents_in_review": docs_in_review,
        },
        "indicators": indicators,
    }
