"""Fachada de leitura para a linha do tempo operacional de um caso.

A fachada normaliza eventos já persistidos nos domínios canônicos. Ela não cria
nova tabela, não duplica escrita e não substitui os registros de origem.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_LEVEL
from app.models.atendimento import Atendimento
from app.models.case import CaseMovimento
from app.models.deadline import Deadline
from app.models.document import DocConfidencialidade, Document
from app.models.legal_doc import LegalDoc
from app.models.process import Process
from app.models.task import Task
from app.models.user import User

_RESTRITOS_PARA_EQUIPE_NAO_SOCIA = (
    DocConfidencialidade.restrito,
    DocConfidencialidade.confidencial,
    DocConfidencialidade.segredo_justica,
)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _as_utc(value: datetime | date | None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _event(
    *,
    entity_id: str,
    kind: str,
    title: str,
    occurred_at: datetime | date | None,
    source: str,
    description: str | None = None,
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_at = _as_utc(occurred_at)
    return {
        "id": f"{source}:{entity_id}",
        "entity_id": entity_id,
        "kind": kind,
        "title": title,
        "description": description,
        "status": status,
        "source": source,
        "occurred_at": normalized_at.isoformat(),
        "metadata": metadata or {},
        "_sort_at": normalized_at,
    }


def _role_value(user: User) -> str:
    role = getattr(user, "role", "")
    return str(getattr(role, "value", role) or "")


def _document_query(user: User, case_id: str, source_limit: int) -> Select[Any]:
    query = select(Document).where(
        Document.case_id == case_id,
        Document.deleted_at.is_(None),
    )
    if ROLE_LEVEL.get(_role_value(user), 0) < ROLE_LEVEL["socio"]:
        query = query.where(
            Document.confidencialidade.notin_(_RESTRITOS_PARA_EQUIPE_NAO_SOCIA)
        )
    return query.order_by(Document.created_at.desc()).limit(source_limit)


def _register_saturation(
    rows: list[Any], source: str, source_limit: int, saturated: list[str]
) -> None:
    if len(rows) >= source_limit:
        saturated.append(source)


async def timeline(
    db: AsyncSession,
    user: User,
    case_id: str,
    *,
    page: int = 1,
    per_page: int = 50,
    source_limit: int = 500,
) -> dict[str, Any]:
    """Retorna eventos normalizados, respeitando confidencialidade documental."""
    events: list[dict[str, Any]] = []
    saturated_sources: list[str] = []

    movements = list(
        (
            await db.execute(
                select(CaseMovimento)
                .where(CaseMovimento.case_id == case_id)
                .order_by(
                    CaseMovimento.data_evento.desc(),
                    CaseMovimento.created_at.desc(),
                )
                .limit(source_limit)
            )
        )
        .scalars()
        .all()
    )
    _register_saturation(
        movements, "case_movimentos", source_limit, saturated_sources
    )
    events.extend(
        _event(
            entity_id=row.id,
            kind="movement",
            title=f"Movimentação: {_enum_value(row.tipo)}",
            description=row.descricao,
            occurred_at=row.data_evento or row.created_at,
            source="case_movimentos",
            metadata={"resumo_ia": row.resumo_ia},
        )
        for row in movements
    )

    processes = list(
        (
            await db.execute(
                select(Process)
                .where(Process.case_id == case_id, Process.deleted_at.is_(None))
                .order_by(Process.created_at.desc())
                .limit(source_limit)
            )
        )
        .scalars()
        .all()
    )
    _register_saturation(processes, "processes", source_limit, saturated_sources)
    events.extend(
        _event(
            entity_id=row.id,
            kind="process",
            title="Processo principal" if row.is_principal else "Processo vinculado",
            description=row.numero_cnj or "Processo sem numeração informada",
            occurred_at=row.created_at,
            source="processes",
            status=str(row.status or ""),
            metadata={
                "numero_cnj": row.numero_cnj,
                "tipo": row.tipo,
                "tribunal": row.tribunal,
                "is_principal": bool(row.is_principal),
            },
        )
        for row in processes
    )

    documents = list(
        (await db.execute(_document_query(user, case_id, source_limit)))
        .scalars()
        .all()
    )
    _register_saturation(documents, "documents", source_limit, saturated_sources)
    events.extend(
        _event(
            entity_id=row.id,
            kind="document",
            title=row.titulo,
            description=row.filename,
            occurred_at=row.created_at,
            source="documents",
            metadata={
                "tipo": row.tipo,
                "confidencialidade": _enum_value(row.confidencialidade),
                "versao": row.versao,
            },
        )
        for row in documents
    )

    deadlines = list(
        (
            await db.execute(
                select(Deadline)
                .where(Deadline.case_id == case_id, Deadline.deleted_at.is_(None))
                .order_by(Deadline.data_prazo.desc(), Deadline.created_at.desc())
                .limit(source_limit)
            )
        )
        .scalars()
        .all()
    )
    _register_saturation(deadlines, "deadlines", source_limit, saturated_sources)
    events.extend(
        _event(
            entity_id=row.id,
            kind="deadline",
            title=row.titulo,
            description=row.descricao,
            occurred_at=row.data_conclusao or row.data_prazo,
            source="deadlines",
            status=str(_enum_value(row.status) or ""),
            metadata={
                "tipo": _enum_value(row.tipo),
                "prioridade": _enum_value(row.prioridade),
                "confirmado": bool(row.confirmado),
                "ciencia_confirmada": bool(row.ciencia_confirmada),
                "origem": row.origem,
                "responsavel_id": row.responsavel_id,
            },
        )
        for row in deadlines
    )

    tasks = list(
        (
            await db.execute(
                select(Task)
                .where(Task.case_id == case_id, Task.deleted_at.is_(None))
                .order_by(Task.updated_at.desc(), Task.created_at.desc())
                .limit(source_limit)
            )
        )
        .scalars()
        .all()
    )
    _register_saturation(tasks, "tasks", source_limit, saturated_sources)
    events.extend(
        _event(
            entity_id=row.id,
            kind="task",
            title=row.titulo,
            description=row.descricao,
            occurred_at=row.concluida_em or row.updated_at or row.created_at,
            source="tasks",
            status=str(_enum_value(row.status) or ""),
            metadata={
                "prioridade": row.prioridade,
                "data_limite": row.data_limite.isoformat() if row.data_limite else None,
                "responsavel_id": row.responsavel_id,
            },
        )
        for row in tasks
    )

    attendances = list(
        (
            await db.execute(
                select(Atendimento)
                .where(Atendimento.case_id == case_id)
                .order_by(Atendimento.data_atendimento.desc())
                .limit(source_limit)
            )
        )
        .scalars()
        .all()
    )
    _register_saturation(
        attendances, "atendimentos", source_limit, saturated_sources
    )
    events.extend(
        _event(
            entity_id=row.id,
            kind="attendance",
            title=f"Atendimento: {_enum_value(row.tipo)}",
            description=row.resumo,
            occurred_at=row.data_atendimento,
            source="atendimentos",
            status="atendida" if row.solicitacao_atendida else "pendente",
            metadata={
                "solicitacao": row.solicitacao,
                "proximo_passo": row.proximo_passo,
                "prazo_retorno": (
                    row.solicitacao_prazo.isoformat()
                    if row.solicitacao_prazo
                    else None
                ),
                "contato_status": row.contato_status,
                "responsavel_id": row.solicitacao_responsavel_id,
                "task_id": row.task_id,
            },
        )
        for row in attendances
    )

    legal_docs = list(
        (
            await db.execute(
                select(LegalDoc)
                .where(LegalDoc.case_id == case_id, LegalDoc.deleted_at.is_(None))
                .order_by(LegalDoc.updated_at.desc(), LegalDoc.created_at.desc())
                .limit(source_limit)
            )
        )
        .scalars()
        .all()
    )
    _register_saturation(legal_docs, "legal_docs", source_limit, saturated_sources)
    events.extend(
        _event(
            entity_id=row.id,
            kind="legal_document",
            title=row.titulo,
            description=f"Versão {row.versao}",
            occurred_at=(
                row.protocolado_em
                or row.revisado_em
                or row.updated_at
                or row.created_at
            ),
            source="legal_docs",
            status=str(_enum_value(row.status) or ""),
            metadata={
                "tipo_peca": _enum_value(row.tipo_peca),
                "codigo_peca": row.codigo_peca,
                "ai_generated": bool(row.ai_generated),
                "human_reviewed": bool(row.human_reviewed),
                "numero_protocolo": row.numero_protocolo,
            },
        )
        for row in legal_docs
    )

    events.sort(key=lambda item: (item["_sort_at"], item["id"]), reverse=True)
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
        "saturated_sources": sorted(set(saturated_sources)),
        "items": events[start:end],
    }
