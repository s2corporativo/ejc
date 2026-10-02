from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.security import requer_equipe_juridica
from app.models.ai_learning import AILearningEvent, AILearningEventType
from app.models.ai_log import AILog, pseudonimizar_texto_auditoria
from app.models.case import Case

DIFFICULTIES = {"normal", "complexo", "fronteira", "excepcional"}
SEVERITIES = {"baixa", "media", "alta", "critica"}


def _role(user) -> str:
    raw = getattr(user, "role", "")
    return str(getattr(raw, "value", raw) or "")


async def register_correction(
    db: AsyncSession,
    *,
    user,
    ai_log_id: str,
    corrected_text: str,
    reason: str,
    error_type: str | None = None,
    severity: str | None = None,
    difficulty: str | None = None,
    area: str | None = None,
    source_refs: list[dict[str, Any]] | None = None,
) -> AILearningEvent:
    requer_equipe_juridica(user, "Correções da IA são restritas à equipe jurídica.")
    if difficulty and difficulty not in DIFFICULTIES:
        raise HTTPException(422, "Dificuldade inválida.")
    if severity and severity not in SEVERITIES:
        raise HTTPException(422, "Severidade inválida.")

    log = await db.get(AILog, ai_log_id)
    if not log:
        raise HTTPException(404, "Registro de IA não encontrado.")
    if str(log.user_id) != str(user.id) and not is_gestao(user):
        # Não revelar existência de log de outro usuário.
        raise HTTPException(404, "Registro de IA não encontrado.")

    resolved_area = (area or "").strip().lower() or None
    if resolved_area is None and log.case_id:
        case = await db.get(Case, log.case_id)
        if case is not None:
            raw_area = getattr(case.area, "value", case.area)
            resolved_area = str(raw_area or "").strip().lower() or None

    try:
        _refs_text = pseudonimizar_texto_auditoria(
            json.dumps(source_refs or [], ensure_ascii=False)
        )
        safe_source_refs = json.loads(_refs_text or "[]")
        if not isinstance(safe_source_refs, list):
            safe_source_refs = []
    except Exception:
        safe_source_refs = []

    event = AILearningEvent(
        id=str(uuid4()),
        ai_log_id=log.id,
        case_id=log.case_id,
        created_by=user.id,
        event_type=AILearningEventType.correction,
        area=resolved_area,
        difficulty=difficulty,
        error_type=(error_type or "").strip().lower() or None,
        severity=severity,
        original_text=log.resposta or "",
        corrected_text=corrected_text,
        reason=reason,
        source_refs=safe_source_refs,
        metadata_json={
            "model": log.modelo,
            "tipo_uso": getattr(log.tipo_uso, "value", str(log.tipo_uso)),
            "origin": "human_correction",
            "creator_role": _role(user),
        },
        approved=False,
        benchmark_eligible=False,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def review_event(
    db: AsyncSession,
    *,
    user,
    event_id: str,
    approved: bool,
    notes: str | None = None,
) -> AILearningEvent:
    requer_equipe_juridica(user, "Revisão do aprendizado é restrita à equipe jurídica.")
    event = await db.get(AILearningEvent, event_id)
    if not event:
        raise HTTPException(404, "Evento de aprendizado não encontrado.")
    if event.case_id:
        # Correções podem conter estratégia/prova do caso, ainda que
        # pseudonimizadas. O ID do evento nunca pode furar o ownership.
        await verificar_acesso_caso(db, user, str(event.case_id))

    # Para transformar correção em gold/benchmark, exige revisão independente.
    independent = str(event.created_by or "") != str(user.id)
    if approved and not independent:
        raise HTTPException(
            409,
            "Aprovação do aprendizado exige revisor humano independente do autor.",
        )
    eligible = bool(
        approved
        and independent
        and event.event_type == AILearningEventType.correction
        and (event.corrected_text or "").strip()
        and (event.reason or "").strip()
    )

    event.approved = bool(approved)
    event.benchmark_eligible = eligible
    event.approved_by = user.id
    event.approved_at = datetime.now(timezone.utc)
    meta = dict(event.metadata_json or {})
    meta.update({
        "review_notes": (notes or "")[:2000],
        "independent_review": independent,
        "reviewer_role": _role(user),
    })
    event.metadata_json = meta

    if event.ai_log_id:
        log = await db.get(AILog, event.ai_log_id)
        if log is not None:
            log.feedback = "corrigido" if approved else "rejeitado"
            log.feedback_em = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(event)
    return event


async def approved_learning_context(
    db: AsyncSession,
    *,
    area: str | None,
    limit: int = 3,
) -> str:
    """Lições humanas aprovadas; nunca substituem fonte jurídica oficial."""
    q = (
        select(AILearningEvent)
        .where(
            AILearningEvent.approved.is_(True),
            AILearningEvent.benchmark_eligible.is_(True),
            AILearningEvent.event_type == AILearningEventType.correction,
        )
        .order_by(AILearningEvent.approved_at.desc(), AILearningEvent.created_at.desc())
        .limit(max(1, min(limit, 5)))
    )
    if area:
        q = q.where(
            (AILearningEvent.area == area)
            | (AILearningEvent.area.is_(None))
        )
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return ""

    blocks: list[str] = []
    for row in rows:
        # Não injeta a resposta corrigida completa em outros casos: mesmo
        # pseudonimizada, ela pode carregar estratégia/fatos reconhecíveis.
        # O aprendizado operacional entre casos usa SOMENTE a justificativa
        # generalizada do revisor independente.
        review_note = str((row.metadata_json or {}).get("review_notes") or "").strip()[:900]
        if not review_note:
            continue
        tag = row.error_type or "correcao_humana"
        blocks.append(
            f"- [{tag}] LIÇÃO GENERALIZADA PELO REVISOR: {review_note}"
        )
    if not blocks:
        return ""
    return (
        "LIÇÕES INTERNAS APROVADAS PELO ESCRITÓRIO\n"
        "Use como alerta metodológico, nunca como autoridade jurídica. "
        "Fonte oficial vigente e fatos do caso prevalecem.\n"
        + "\n".join(blocks)
    )


async def pending_learning_events(
    db: AsyncSession,
    *,
    user,
    limit: int = 50,
    independent_only: bool = True,
) -> list[dict[str, Any]]:
    """Fila de curadoria; texto já foi pseudonimizado na persistência."""
    requer_equipe_juridica(user, "Curadoria do aprendizado é restrita à equipe jurídica.")
    q = (
        select(AILearningEvent)
        .where(AILearningEvent.approved.is_(False))
        .order_by(AILearningEvent.created_at.asc())
        .limit(max(1, min(limit, 100)))
    )
    if independent_only:
        q = q.where(
            (AILearningEvent.created_by.is_(None))
            | (AILearningEvent.created_by != user.id)
        )
    rows = (await db.execute(q)).scalars().all()
    visible: list[AILearningEvent] = []
    for row in rows:
        if row.case_id and not is_gestao(user):
            try:
                await verificar_acesso_caso(db, user, str(row.case_id))
            except HTTPException:
                continue
        visible.append(row)

    return [
        {
            "id": row.id,
            "ai_log_id": row.ai_log_id,
            "case_id": row.case_id,
            "event_type": getattr(row.event_type, "value", str(row.event_type)),
            "area": row.area,
            "difficulty": row.difficulty,
            "error_type": row.error_type,
            "severity": row.severity,
            "original_text": row.original_text,
            "corrected_text": row.corrected_text,
            "reason": row.reason,
            "source_refs": row.source_refs or [],
            "created_by": row.created_by,
            "created_at": row.created_at,
            "independent_review_required": True,
        }
        for row in visible
    ]


async def error_memory(
    db: AsyncSession,
    *,
    area: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    q = select(AILearningEvent).where(
        AILearningEvent.approved.is_(True),
        AILearningEvent.error_type.is_not(None),
    )
    if area:
        q = q.where(AILearningEvent.area == area)
    q = q.order_by(AILearningEvent.approved_at.desc()).limit(max(1, min(limit, 200)))
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": row.id,
            "area": row.area,
            "error_type": row.error_type,
            "severity": row.severity,
            "reason": row.reason,
            "difficulty": row.difficulty,
            "benchmark_eligible": row.benchmark_eligible,
            "approved_at": row.approved_at,
        }
        for row in rows
    ]


async def learning_summary(db: AsyncSession) -> dict[str, Any]:
    total = int((await db.execute(select(func.count()).select_from(AILearningEvent))).scalar() or 0)
    approved = int((await db.execute(
        select(func.count()).select_from(AILearningEvent).where(AILearningEvent.approved.is_(True))
    )).scalar() or 0)
    eligible = int((await db.execute(
        select(func.count()).select_from(AILearningEvent).where(
            AILearningEvent.benchmark_eligible.is_(True)
        )
    )).scalar() or 0)
    by_area = {
        str(area or "sem_area"): int(n)
        for area, n in (await db.execute(
            select(AILearningEvent.area, func.count())
            .where(AILearningEvent.approved.is_(True))
            .group_by(AILearningEvent.area)
        )).all()
    }
    by_error = {
        str(error): int(n)
        for error, n in (await db.execute(
            select(AILearningEvent.error_type, func.count())
            .where(
                AILearningEvent.approved.is_(True),
                AILearningEvent.error_type.is_not(None),
            )
            .group_by(AILearningEvent.error_type)
        )).all()
    }
    return {
        "events": total,
        "approved": approved,
        "benchmark_eligible": eligible,
        "by_area": by_area,
        "error_memory": by_error,
        "rule": "correção só entra no benchmark após revisão humana independente",
    }
