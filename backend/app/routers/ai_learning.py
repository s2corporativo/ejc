from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao
from app.core.security import get_current_user, requer_equipe_juridica
from app.models.audit_log import criar_audit_log
from app.models.case import Case, CaseStatus
from app.models.user import User
from app.services.ai.supervised_learning import (
    error_memory,
    learning_summary,
    pending_learning_events,
    register_correction,
    review_event,
)

router = APIRouter(prefix="/ia-learning", tags=["IA — Aprendizado Supervisionado"])


def _staff(cu: User = Depends(get_current_user)) -> User:
    requer_equipe_juridica(cu, "Aprendizado da IA é restrito à equipe jurídica.")
    return cu


class CorrectionIn(BaseModel):
    ai_log_id: str = Field(min_length=36, max_length=36)
    corrected_text: str = Field(min_length=20, max_length=30000)
    reason: str = Field(min_length=10, max_length=4000)
    error_type: str | None = Field(default=None, max_length=80)
    severity: str | None = Field(default=None, pattern="^(baixa|media|alta|critica)$")
    difficulty: str | None = Field(
        default=None, pattern="^(normal|complexo|fronteira|excepcional)$"
    )
    area: str | None = Field(default=None, max_length=80)
    source_refs: list[dict] = Field(default_factory=list, max_length=20)


class ReviewIn(BaseModel):
    approved: bool
    notes: str | None = Field(default=None, max_length=2000)


@router.post("/corrections")
async def create_correction(
    body: CorrectionIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_staff),
):
    event = await register_correction(
        db,
        user=cu,
        ai_log_id=body.ai_log_id,
        corrected_text=body.corrected_text,
        reason=body.reason,
        error_type=body.error_type,
        severity=body.severity,
        difficulty=body.difficulty,
        area=body.area,
        source_refs=body.source_refs,
    )
    await criar_audit_log(
        db,
        user_id=cu.id,
        user_role=getattr(cu.role, "value", str(cu.role)),
        acao="AI_LEARNING_CORRECTION",
        entidade="ai_learning_events",
        registro_id=event.id,
        detalhes=(
            f"Correção humana criada; ai_log={body.ai_log_id}; "
            f"error_type={body.error_type or 'nao_informado'}"
        ),
    )
    await db.commit()
    return {
        "id": event.id,
        "approved": event.approved,
        "benchmark_eligible": event.benchmark_eligible,
        "message": "Correção registrada para revisão humana independente.",
    }


@router.post("/{event_id}/review")
async def review_learning(
    event_id: str,
    body: ReviewIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_staff),
):
    event = await review_event(
        db, user=cu, event_id=event_id, approved=body.approved, notes=body.notes
    )
    await criar_audit_log(
        db,
        user_id=cu.id,
        user_role=getattr(cu.role, "value", str(cu.role)),
        acao="AI_LEARNING_REVIEW",
        entidade="ai_learning_events",
        registro_id=event.id,
        detalhes=(
            f"approved={event.approved}; benchmark_eligible={event.benchmark_eligible}; "
            f"independent_review={(event.metadata_json or {}).get('independent_review')}"
        ),
    )
    await db.commit()
    return {
        "id": event.id,
        "approved": event.approved,
        "benchmark_eligible": event.benchmark_eligible,
        "independent_review": (event.metadata_json or {}).get("independent_review"),
    }


@router.get("/summary")
async def summary(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_staff),
):
    return await learning_summary(db)


@router.get("/pending")
async def pending(
    limit: int = Query(default=50, ge=1, le=100),
    independent_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_staff),
):
    return {
        "data": await pending_learning_events(
            db, user=cu, limit=limit, independent_only=independent_only
        )
    }


@router.get("/errors")
async def errors(
    area: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_staff),
):
    return {"data": await error_memory(db, area=area, limit=limit)}


@router.post("/outcomes/backfill")
async def backfill_outcomes(
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_staff),
):
    """Reaplica o aprendizado já existente apenas a casos encerrados sem memória.

    Idempotência real fica em case_intel.aprendizado_encerramento. Não cria
    resultado, tese ou fato artificial; só processa casos cujo desfecho já foi
    registrado no EJC.
    """
    if not is_gestao(cu):
        raise HTTPException(403, "Backfill de aprendizado exige perfil de gestão.")

    from app.services.case_intel import aprendizado_encerramento

    rows = (
        await db.execute(
            select(Case.id).where(
                Case.deleted_at.is_(None),
                Case.status.in_([CaseStatus.encerrado, CaseStatus.arquivado]),
            )
        )
    ).scalars().all()

    for case_id in rows:
        background.add_task(aprendizado_encerramento, str(case_id))

    return {
        "scheduled": len(rows),
        "message": (
            "Casos encerrados/arquivados enfileirados; a rotina existente é "
            "idempotente e ignora aprendizado já registrado."
        ),
    }
