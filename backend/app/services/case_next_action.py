# ── app/services/case_next_action.py ─────────────────────────────────────────
"""Núcleo operacional do caso: ação atual, exceção e estado derivado.

O estado jurídico continua pertencendo ao LegalCaseOrchestrator. Este serviço
trata somente a responsabilidade operacional: o que fazer, por quem, até quando
e a partir de qual registro.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ownership import pode_ver_todos
from app.models.audit_log import criar_audit_log
from app.models.case import Case, CaseMovimento, CaseStatus
from app.models.case_next_action import CaseNextAction, CaseNextActionWaiver
from app.models.deadline import Deadline
from app.models.document import Document
from app.models.task import Task
from app.models.user import User, UserRole
from app.schemas.case_next_action import (
    CaseNextActionComplete,
    CaseNextActionCreate,
    CaseNextActionWaiverCreate,
)

settings = get_settings()
OPEN_STATUSES = {
    CaseStatus.triagem,
    CaseStatus.ativo,
    CaseStatus.suspenso,
    CaseStatus.acordo,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def current_action(
    db: AsyncSession,
    case_id: str,
    *,
    lock: bool = False,
) -> CaseNextAction | None:
    query = select(CaseNextAction).where(
        CaseNextAction.case_id == case_id,
        CaseNextAction.completed_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


async def open_waiver(
    db: AsyncSession,
    case_id: str,
    *,
    lock: bool = False,
) -> CaseNextActionWaiver | None:
    """Registro não revogado, inclusive expirado, para revogação idempotente."""
    query = select(CaseNextActionWaiver).where(
        CaseNextActionWaiver.case_id == case_id,
        CaseNextActionWaiver.revoked_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


async def current_waiver(
    db: AsyncSession,
    case_id: str,
    *,
    now: datetime | None = None,
) -> CaseNextActionWaiver | None:
    now = now or _utcnow()
    return (
        await db.execute(
            select(CaseNextActionWaiver).where(
                CaseNextActionWaiver.case_id == case_id,
                CaseNextActionWaiver.revoked_at.is_(None),
                CaseNextActionWaiver.expires_at > now,
            )
        )
    ).scalar_one_or_none()


def derive_operational_state(
    case: Case,
    action: CaseNextAction | None,
    waiver: CaseNextActionWaiver | None,
    *,
    now: datetime | None = None,
) -> str:
    """Estado operacional controlado, derivado; não duplica o workflow jurídico."""
    now = now or _utcnow()
    if case.status in (CaseStatus.encerrado, CaseStatus.arquivado):
        return "encerrado"
    if case.status == CaseStatus.acordo:
        return "negociacao"

    if action is not None and action.blocked:
        if action.waiting_on == "cliente":
            return "aguardando_cliente"
        if action.waiting_on in ("terceiro", "tribunal"):
            return "aguardando_terceiro"

    if action is not None:
        due_at = _aware(action.due_at)
        if action.urgency == "critica" or due_at <= now + timedelta(days=3):
            return "providencia_urgente"
        return "em_andamento"

    if case.status == CaseStatus.triagem:
        return "onboarding"
    if case.status == CaseStatus.suspenso:
        return "aguardando_terceiro"
    if waiver is not None:
        return "planejamento"
    return "planejamento"


async def operational_view(db: AsyncSession, case: Case) -> dict:
    action = await current_action(db, case.id)
    waiver = await current_waiver(db, case.id)
    return {
        "case_id": case.id,
        "estado_operacional": derive_operational_state(case, action, waiver),
        "next_action": action,
        "waiver": waiver,
        "enforcement_enabled": settings.CASE_NEXT_ACTION_ENFORCEMENT,
    }


async def _validate_owner(
    db: AsyncSession,
    case: Case,
    actor: User,
    owner_id: str,
) -> User:
    owner = (
        await db.execute(
            select(User).where(
                User.id == owner_id,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if owner is None or owner.role == UserRole.cliente_externo:
        raise HTTPException(
            status_code=422,
            detail="Responsável deve ser um usuário interno ativo",
        )

    if not pode_ver_todos(actor):
        allowed = {
            actor.id,
            case.advogado_responsavel_id,
            case.advogado_auxiliar_id,
        }
        if owner_id not in {item for item in allowed if item}:
            raise HTTPException(
                status_code=403,
                detail="Não é permitido atribuir a ação a este usuário",
            )
    return owner


async def _validate_origin(
    db: AsyncSession,
    case_id: str,
    origin_type: str,
    origin_id: str | None,
) -> None:
    if origin_type == "manual":
        return

    model = {
        "documento": Document,
        "movimento": CaseMovimento,
        "prazo": Deadline,
        "tarefa": Task,
    }[origin_type]
    filters = [model.id == origin_id, model.case_id == case_id]
    if hasattr(model, "deleted_at"):
        filters.append(model.deleted_at.is_(None))
    exists = (await db.execute(select(model.id).where(*filters))).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=422,
            detail="A origem informada não pertence ao caso ou não está ativa",
        )


def _new_action(
    case_id: str,
    actor_id: str,
    payload: CaseNextActionCreate,
) -> CaseNextAction:
    return CaseNextAction(
        id=str(uuid4()),
        case_id=case_id,
        title=payload.title,
        owner_id=payload.owner_id,
        due_at=payload.due_at,
        urgency=payload.urgency,
        blocked=payload.blocked,
        blocked_reason=payload.blocked_reason,
        waiting_on=payload.waiting_on,
        origin_type=payload.origin_type,
        origin_id=payload.origin_id,
        created_by=actor_id,
    )


def _complete(
    action: CaseNextAction,
    actor_id: str,
    note: str | None,
    *,
    now: datetime,
) -> None:
    action.completed_at = now
    action.completed_by = actor_id
    action.completion_note = note


def _new_waiver(
    case_id: str,
    actor_id: str,
    payload: CaseNextActionWaiverCreate,
) -> CaseNextActionWaiver:
    return CaseNextActionWaiver(
        id=str(uuid4()),
        case_id=case_id,
        reason=payload.reason,
        expires_at=payload.expires_at,
        created_by=actor_id,
    )


def _timeline(
    case_id: str,
    actor_id: str,
    tipo: str,
    descricao: str,
) -> CaseMovimento:
    return CaseMovimento(
        id=str(uuid4()),
        case_id=case_id,
        tipo=tipo,
        descricao=descricao,
        data_evento=_utcnow(),
        created_by=actor_id,
    )


async def set_next_action(
    db: AsyncSession,
    case: Case,
    actor: User,
    payload: CaseNextActionCreate,
) -> dict:
    if case.status not in OPEN_STATUSES:
        raise HTTPException(409, "Caso encerrado/arquivado não recebe próxima ação")

    await _validate_owner(db, case, actor, payload.owner_id)
    await _validate_origin(db, case.id, payload.origin_type, payload.origin_id)

    now = _utcnow()
    previous = await current_action(db, case.id, lock=True)
    if previous is not None:
        _complete(
            previous,
            actor.id,
            "Substituída por nova próxima ação",
            now=now,
        )
        db.add(
            _timeline(
                case.id,
                actor.id,
                "acao_substituida",
                f"Próxima ação substituída: {previous.title}",
            )
        )

    waiver = await open_waiver(db, case.id, lock=True)
    if waiver is not None:
        waiver.revoked_at = now
        waiver.revoked_by = actor.id

    action = _new_action(case.id, actor.id, payload)
    db.add(action)
    db.add(
        _timeline(
            case.id,
            actor.id,
            "proxima_acao",
            f"Próxima ação definida: {action.title} — responsável {action.owner_id}",
        )
    )
    await criar_audit_log(
        db,
        actor.id,
        actor.role.value,
        "SET_NEXT_ACTION",
        "case_next_actions",
        action.id,
        dados_depois={
            "case_id": case.id,
            "owner_id": action.owner_id,
            "due_at": action.due_at.isoformat(),
            "urgency": action.urgency,
            "blocked": action.blocked,
            "origin_type": action.origin_type,
            "origin_id": action.origin_id,
        },
    )
    await db.commit()
    return await operational_view(db, case)


async def complete_next_action(
    db: AsyncSession,
    case: Case,
    actor: User,
    payload: CaseNextActionComplete,
) -> dict:
    action = await current_action(db, case.id, lock=True)
    if action is None:
        raise HTTPException(409, "O caso não possui próxima ação atual")

    if (
        settings.CASE_NEXT_ACTION_ENFORCEMENT
        and case.status in OPEN_STATUSES
        and payload.replacement is None
        and payload.waiver is None
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Caso ativo exige uma nova próxima ação ou exceção "
                "temporária justificada"
            ),
        )

    if payload.replacement is not None:
        await _validate_owner(db, case, actor, payload.replacement.owner_id)
        await _validate_origin(
            db,
            case.id,
            payload.replacement.origin_type,
            payload.replacement.origin_id,
        )

    now = _utcnow()
    _complete(action, actor.id, payload.completion_note, now=now)
    db.add(
        _timeline(
            case.id,
            actor.id,
            "acao_concluida",
            f"Próxima ação concluída: {action.title}",
        )
    )

    replacement = None
    waiver = None
    if payload.replacement is not None:
        replacement = _new_action(case.id, actor.id, payload.replacement)
        db.add(replacement)
        db.add(
            _timeline(
                case.id,
                actor.id,
                "proxima_acao",
                f"Nova próxima ação: {replacement.title}",
            )
        )
    elif payload.waiver is not None:
        prior_waiver = await open_waiver(db, case.id, lock=True)
        if prior_waiver is not None:
            prior_waiver.revoked_at = now
            prior_waiver.revoked_by = actor.id
        waiver = _new_waiver(case.id, actor.id, payload.waiver)
        db.add(waiver)
        db.add(
            _timeline(
                case.id,
                actor.id,
                "acao_dispensada",
                "Caso temporariamente sem próxima ação, com justificativa auditada",
            )
        )

    await criar_audit_log(
        db,
        actor.id,
        actor.role.value,
        "COMPLETE_NEXT_ACTION",
        "case_next_actions",
        action.id,
        dados_depois={
            "case_id": case.id,
            "completion_note": payload.completion_note,
            "replacement_id": replacement.id if replacement else None,
            "waiver_id": waiver.id if waiver else None,
        },
    )
    await db.commit()
    return await operational_view(db, case)


async def waive_next_action(
    db: AsyncSession,
    case: Case,
    actor: User,
    payload: CaseNextActionWaiverCreate,
) -> dict:
    if case.status not in OPEN_STATUSES:
        raise HTTPException(409, "Caso encerrado/arquivado não recebe exceção")

    now = _utcnow()
    action = await current_action(db, case.id, lock=True)
    if action is not None:
        _complete(
            action,
            actor.id,
            "Ação encerrada por exceção operacional temporária",
            now=now,
        )

    prior = await open_waiver(db, case.id, lock=True)
    if prior is not None:
        prior.revoked_at = now
        prior.revoked_by = actor.id

    waiver = _new_waiver(case.id, actor.id, payload)
    db.add(waiver)
    db.add(
        _timeline(
            case.id,
            actor.id,
            "acao_dispensada",
            "Exceção temporária de próxima ação registrada",
        )
    )
    await criar_audit_log(
        db,
        actor.id,
        actor.role.value,
        "WAIVE_NEXT_ACTION",
        "case_next_action_waivers",
        waiver.id,
        dados_depois={
            "case_id": case.id,
            "expires_at": waiver.expires_at.isoformat(),
            "reason": waiver.reason,
        },
    )
    await db.commit()
    return await operational_view(db, case)


async def readiness_issues(db: AsyncSession, case: Case) -> list[dict]:
    """Pendências do núcleo operacional; informativas até o flag ser ativado."""
    if case.status not in OPEN_STATUSES:
        return []

    issues: list[dict] = []
    if not case.advogado_responsavel_id:
        issues.append(
            {
                "codigo": "sem_responsavel",
                "detalhe": "Caso ativo sem advogado responsável",
            }
        )

    action = await current_action(db, case.id)
    waiver = await current_waiver(db, case.id)
    if action is None and waiver is None:
        issues.append(
            {
                "codigo": "sem_proxima_acao",
                "detalhe": "Caso ativo sem próxima ação ou exceção vigente",
            }
        )
    return issues
