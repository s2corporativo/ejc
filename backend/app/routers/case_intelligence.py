# ── app/routers/case_intelligence.py ─────────────────────────────────────────
# FASE 1 do Orquestrador Jurídico — leitura/aprovação do CaseIntelligenceSnapshot.
#
# GET  /cases/{case_id}/inteligencia                → último snapshot + histórico resumido
# GET  /cases/{case_id}/inteligencia/{snapshot_id}  → snapshot completo
# POST /cases/{case_id}/inteligencia/{snapshot_id}/aprovar → HITL: congela (advogado+)
#
# Gates: verificar_acesso_caso (RBAC+ABAC) em TODOS; aprovar exige advogado+
# (mesmo limiar de intake/motor_peca), rate limit e AuditLog (no service).
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.case_intelligence import CaseIntelligenceSnapshot
from app.models.user import User
from app.services import case_intelligence_service as cis

logger = logging.getLogger("ejc.case_intelligence")

router = APIRouter(prefix="/cases/{case_id}/inteligencia",
                   tags=["Inteligência do Caso"])


def _pode_aprovar(cu: User) -> bool:
    """Mesmo limiar de intake/motor_peca: advogado+ (HITL é ato de advogado)."""
    role = getattr(cu.role, "value", cu.role)
    return ROLE_LEVEL.get(role, 0) >= ROLE_LEVEL["advogado"]


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _ser_resumido(s: CaseIntelligenceSnapshot) -> dict:
    return {
        "id": s.id,
        "versao": s.versao,
        "origem": s.origem,
        "resumo": s.resumo,
        "congelado": bool(s.congelado),
        "criado_por": s.criado_por,
        "criado_em": _iso(s.criado_em),
        "aprovado_por": s.aprovado_por,
        "aprovado_em": _iso(s.aprovado_em),
    }


def _ser_completo(s: CaseIntelligenceSnapshot) -> dict:
    out = _ser_resumido(s)
    out["case_id"] = s.case_id
    out["payload"] = s.payload or {}
    out["ai_log_ids"] = s.ai_log_ids or []
    return out


@router.get("")
async def obter_inteligencia(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Último snapshot (completo) + histórico resumido do caso."""
    await verificar_acesso_caso(db, cu, case_id)
    snaps = await cis.historico(db, case_id)
    return {
        "case_id": case_id,
        "total": len(snaps),
        "ultimo": _ser_completo(snaps[0]) if snaps else None,
        "historico": [_ser_resumido(s) for s in snaps],
    }


@router.get("/{snapshot_id}")
async def obter_snapshot(
    case_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Snapshot completo — 404 se não existir OU não pertencer ao caso."""
    await verificar_acesso_caso(db, cu, case_id)
    snap = await cis.obter_snapshot(db, snapshot_id, case_id=case_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado")
    return _ser_completo(snap)


@router.post(
    "/{snapshot_id}/aprovar",
    dependencies=[Depends(rate_limit("inteligencia-aprovar", 10))],
)
async def aprovar(
    case_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """HITL: advogado aprova o snapshot → congelado (imutável) + AuditLog.

    409 se já congelado. Snapshot automático nunca nasce aprovado — este
    endpoint é o ÚNICO caminho de aprovação (ato humano, OAB Prov. 205/2021).
    """
    if not _pode_aprovar(cu):
        raise HTTPException(403, "Aprovação de snapshot restrita a advogados")
    await verificar_acesso_caso(db, cu, case_id)
    snap = await cis.aprovar_snapshot(db, snapshot_id, cu, case_id=case_id)
    return {"ok": True, "snapshot": _ser_resumido(snap)}
