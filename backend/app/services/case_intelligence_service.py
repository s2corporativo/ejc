# ── app/services/case_intelligence_service.py ────────────────────────────────
# FASE 1 do Orquestrador Jurídico — service do CaseIntelligenceSnapshot.
#
# Regras:
#   • criar_snapshot: versao = max+1 por caso — NUNCA sobrescreve (append-only).
#     Snapshot automático nasce congelado=False (HITL: aprovar é ato humano).
#   • aprovar_snapshot: congela (imutável); 409 se já congelado; AuditLog.
#   • gravar_snapshot_seguro: wrapper FAIL-SAFE usado pelo wiring (triagem/
#     intake/motor_peca) — falha de snapshot NUNCA quebra o fluxo original.
#   • compactar_payload: garante payload ≤ ~50KB (motor_peca) sem textos gigantes.
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.audit_log import criar_audit_log
from app.models.case_intelligence import CaseIntelligenceSnapshot, ORIGENS_SNAPSHOT
from app.models.user import User

logger = logging.getLogger("ejc.case_intelligence")

# Limite prático do payload (motor_peca e afins): ~50KB serializado.
PAYLOAD_MAX_BYTES = 50_000

# Corte defensivo de strings no último recurso da compactação.
_TRUNC_STR = 2_000


async def criar_snapshot(
    db,
    case_id: str,
    origem: str,
    payload: dict,
    resumo: str | None = None,
    ai_log_ids: list[str] | None = None,
    criado_por: str | None = None,
) -> CaseIntelligenceSnapshot:
    """Grava um snapshot NOVO (versao = max+1 do caso — nunca sobrescreve).

    Snapshot nasce SEMPRE congelado=False (HITL — aprovação é ato humano).
    Commit aqui mesmo: o índice único (case_id, versao) garante que corrida no
    max+1 vira IntegrityError — re-tentado UMA vez com a versão recalculada
    (auditoria 8a); persistindo, propaga (o wrapper fail-safe absorve nos
    fluxos automáticos).
    """
    if origem not in ORIGENS_SNAPSHOT:
        raise ValueError(f"origem inválida: {origem!r} (válidas: {ORIGENS_SNAPSHOT})")
    if not isinstance(payload, dict):
        raise ValueError("payload deve ser um dict (estrutura documentada no model)")

    for tentativa in (1, 2):
        max_versao = (await db.execute(
            select(func.max(CaseIntelligenceSnapshot.versao))
            .where(CaseIntelligenceSnapshot.case_id == case_id)
        )).scalar()
        snap = CaseIntelligenceSnapshot(
            id=str(uuid4()),
            case_id=case_id,
            versao=(max_versao or 0) + 1,
            origem=origem,
            payload=payload,
            resumo=(resumo or None),
            ai_log_ids=list(ai_log_ids or []),
            criado_por=criado_por,
            congelado=False,          # NUNCA nasce aprovado
            aprovado_por=None,
            aprovado_em=None,
        )
        db.add(snap)
        try:
            await db.commit()
            return snap
        except IntegrityError:
            await db.rollback()
            if tentativa == 2:
                raise
    raise RuntimeError("criar_snapshot: corrida de versão não resolvida")


async def gravar_snapshot_seguro(db, **kwargs) -> CaseIntelligenceSnapshot | None:
    """Wrapper FAIL-SAFE para o wiring automático (triagem/intake/motor_peca).

    Qualquer falha vira log warning + rollback best-effort — o fluxo de origem
    segue intacto. (Seguro: os fluxos de origem já commitaram seus próprios
    dados antes de chegar aqui — AILog commita em _log_ia; triagem commita
    antes do snapshot.)
    """
    try:
        return await criar_snapshot(db, **kwargs)
    except Exception as e:  # noqa: BLE001 — fail-safe por contrato
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning(
            "[case_intelligence] Snapshot não gravado (fluxo original preservado) "
            f"case={kwargs.get('case_id')} origem={kwargs.get('origem')}: {str(e)[:200]}"
        )
        return None


async def ultimo_snapshot(db, case_id: str) -> CaseIntelligenceSnapshot | None:
    """Último snapshot (maior versão) do caso, ou None."""
    return (await db.execute(
        select(CaseIntelligenceSnapshot)
        .where(CaseIntelligenceSnapshot.case_id == case_id)
        .order_by(CaseIntelligenceSnapshot.versao.desc())
        .limit(1)
    )).scalar_one_or_none()


async def historico(db, case_id: str) -> list[CaseIntelligenceSnapshot]:
    """Todos os snapshots do caso, mais recente primeiro."""
    return list((await db.execute(
        select(CaseIntelligenceSnapshot)
        .where(CaseIntelligenceSnapshot.case_id == case_id)
        .order_by(CaseIntelligenceSnapshot.versao.desc())
    )).scalars().all())


async def obter_snapshot(
    db, snapshot_id: str, case_id: str | None = None,
) -> CaseIntelligenceSnapshot | None:
    """Snapshot por id; com case_id, também confere o vínculo (anti-IDOR)."""
    q = select(CaseIntelligenceSnapshot).where(
        CaseIntelligenceSnapshot.id == snapshot_id)
    if case_id is not None:
        q = q.where(CaseIntelligenceSnapshot.case_id == case_id)
    return (await db.execute(q)).scalar_one_or_none()


async def aprovar_snapshot(
    db, snapshot_id: str, user: User, case_id: str | None = None,
) -> CaseIntelligenceSnapshot:
    """Aprovação HUMANA (HITL): congela o snapshot — imutável a partir daqui.

    404 se não existe (ou não pertence ao case_id informado); 409 se já
    congelado. Auditoria via criar_audit_log (mesma transação).
    """
    snap = await obter_snapshot(db, snapshot_id, case_id=case_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot não encontrado")
    if snap.congelado:
        raise HTTPException(status_code=409, detail="Snapshot já aprovado/congelado")

    snap.congelado = True
    snap.aprovado_por = user.id
    snap.aprovado_em = datetime.now(timezone.utc)
    # Corrida (auditoria 8c): check-then-set mantido. Limite documentado:
    # aprovação dupla SIMULTÂNEA do mesmo snapshot não é detectável sem
    # SELECT ... FOR UPDATE (re-select na mesma transação devolve o próprio
    # objeto do identity map); o efeito é idempotente (congelado=True) e o
    # 409 acima cobre o caso sequencial — AuditLog registra cada aprovação.

    role = getattr(user.role, "value", None) or str(getattr(user, "role", "") or "")
    await criar_audit_log(
        db, user_id=user.id, user_role=role,
        acao="UPDATE", entidade="case_intelligence_snapshots",
        registro_id=snap.id,
        detalhes=f"Snapshot de inteligência v{snap.versao} do caso {snap.case_id} "
                 f"aprovado e congelado (origem={snap.origem})",
    )
    await db.commit()
    return snap


def compactar_payload(
    payload: dict,
    max_bytes: int = PAYLOAD_MAX_BYTES,
    descartaveis: tuple[str, ...] = (),
) -> dict:
    """Garante payload serializado ≤ max_bytes SEM os textos gigantes.

    1) Se já cabe, devolve cópia intacta.
    2) Remove chaves `descartaveis` (na ordem) até caber, anotando em
       `_compactado` o que foi retirado (transparência p/ o revisor).
    3) Último recurso: trunca strings longas em toda a árvore.
    """
    def _tam(d: dict) -> int:
        return len(json.dumps(d, ensure_ascii=False, default=str).encode("utf-8"))

    data = dict(payload)
    if _tam(data) <= max_bytes:
        return data

    removidas: list[str] = []
    for k in descartaveis:
        if k in data:
            data.pop(k)
            removidas.append(k)
            data["_compactado"] = removidas
            if _tam(data) <= max_bytes:
                return data

    def _trunca(v):
        if isinstance(v, str) and len(v) > _TRUNC_STR:
            return v[:_TRUNC_STR] + "… [truncado]"
        if isinstance(v, dict):
            return {k: _trunca(x) for k, x in v.items()}
        if isinstance(v, list):
            return [_trunca(x) for x in v]
        return v

    data = _trunca(data)
    # Transparência: a truncagem de strings também fica anotada em _compactado
    # (auditoria 17) e o tamanho é RE-verificado — acima do teto mesmo após o
    # último recurso, registra warning (payload segue, mas rastreável).
    data["_compactado"] = [*removidas, "strings_truncadas"]
    if _tam(data) > max_bytes:
        logger.warning(
            "[case_intelligence] payload ainda acima de %d bytes após "
            "truncagem (%d bytes)", max_bytes, _tam(data))
    return data
