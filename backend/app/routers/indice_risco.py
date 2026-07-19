# ── app/routers/indice_risco.py ───────────────────────────────────────────────
from __future__ import annotations
import json
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user, requer_advogado
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.audit_log import criar_audit_log

router = APIRouter(prefix="/cases/{case_id}/indice-risco", tags=["Índice de Risco"])


def _nivel(indice: int) -> str:
    if indice <= 25: return "baixo"
    if indice <= 50: return "medio"
    if indice <= 75: return "alto"
    return "critico"


@router.get("")
async def get_indice(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)  # IDOR (auditoria 2026-06-30)
    atual = await db.execute(
        text("SELECT indice_risco, risco_nivel, risco_fatores FROM cases WHERE id = :id"),
        {"id": case_id},
    )
    hist = await db.execute(
        text("""
            SELECT indice, nivel, fatores, calculado_por, created_at
            FROM indice_risco_historico WHERE case_id = :cid
            ORDER BY created_at DESC LIMIT 20
        """),
        {"cid": case_id},
    )
    return {
        "atual": dict(atual.mappings().first() or {}),
        "historico": [dict(r) for r in hist.mappings().all()],
    }


@router.post("/recalcular")
async def recalcular(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    requer_advogado(cu)  # [B2] escrita: piso advogado+ (irmãos score_juridico/sala)
    await verificar_acesso_caso(db, cu, case_id)  # IDOR (auditoria 2026-06-30)
    # Calcular baseado em dados objetivos
    r = await db.execute(
        text("""
            SELECT c.valor_causa,
                   EXTRACT(DAYS FROM NOW() - c.created_at) AS dias,
                   COUNT(DISTINCT dl.id) FILTER (
                       WHERE dl.data_prazo < CURRENT_DATE AND dl.status != 'concluido'
                   ) AS prazos_vencidos,
                   COUNT(DISTINCT d.id) AS total_docs
            FROM cases c
            LEFT JOIN deadlines dl ON dl.case_id = c.id
            LEFT JOIN documents d ON d.case_id = c.id
            WHERE c.id = :cid
            GROUP BY c.id
        """),
        {"cid": case_id},
    )
    data = r.mappings().first()
    if not data:
        from fastapi import HTTPException
        raise HTTPException(404, "Caso não encontrado")

    fatores = {}
    indice = 0
    prazos = int(data["prazos_vencidos"] or 0)
    if prazos > 0:
        fatores["prazo_vencido"] = True
        indice += min(30, prazos * 15)
    if int(data["total_docs"] or 0) == 0:
        fatores["sem_documentos"] = True
        indice += 15
    valor = float(data["valor_causa"] or 0)
    if valor > 500_000:
        fatores["valor_alto"] = True
        indice += 10
    elif valor > 100_000:
        fatores["valor_medio"] = True
        indice += 5
    if float(data["dias"] or 0) > 365 * 3:
        fatores["processo_antigo"] = True
        indice += 10
    indice = min(indice, 100)
    nivel = _nivel(indice)

    # Salvar histórico
    await db.execute(
        text("""
            INSERT INTO indice_risco_historico
                (case_id, indice, nivel, fatores, calculado_por)
            VALUES (:cid, :ind, :niv, :fat, 'sistema')
        """),
        {"cid": case_id, "ind": indice, "niv": nivel, "fat": json.dumps(fatores)},
    )
    await db.execute(
        text("""
            UPDATE cases
            SET indice_risco=:ind, risco_nivel=:niv, risco_fatores=:fat,
                risco_atualizado_em=NOW()
            WHERE id=:cid
        """),
        {"cid": case_id, "ind": indice, "niv": nivel, "fat": json.dumps(fatores)},
    )
    await criar_audit_log(
        db, cu.id, cu.role.value, "UPDATE", "indice_risco", case_id,
        dados_depois={"indice": indice, "nivel": nivel},
    )
    await db.commit()
    return {"indice": indice, "nivel": nivel, "fatores": fatores}
