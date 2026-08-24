# ── app/routers/teses_evidencia_import.py ────────────────────────────────────
# Coleta de evidência jurídica (legal_evidence) para uma tese específica, via
# as MESMAS fontes oficiais do pipeline de importação de jurisprudência já
# existente (app/routers/juris_import.py) — mesmo padrão de rota, RBAC, rate
# limit e job assíncrono; destino de gravação diferente (legal_evidence, não
# knowledge_docs). Ver app/services/teses_evidencia_import.py.
#
#   POST /teses/{tese_id}/evidencias/coletar                  (advogado+, 3/min)
#        → dispara job em BackgroundTasks; resposta 202 com job_id.
#   GET  /teses/{tese_id}/evidencias/coletar/status/{job_id}  (autenticado, ownership)
#        → status consultável do job ({importados, duplicados, erros}).
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.routers.teses import _pode_editar, _tese_ou_404
from app.services.juris_import import FONTES
from app.services.teses_evidencia_import import executar_coleta_evidencia, status_job

router = APIRouter(prefix="/teses", tags=["Banco de Teses — Coleta de Evidência"])


class ColetarEvidenciaRequest(BaseModel):
    fonte: str = Field(..., max_length=30)
    consulta: str = Field(..., min_length=3, max_length=300)
    tribunal: Optional[str] = Field(None, max_length=20)
    limite: int = Field(20, ge=1, le=100)
    ano: Optional[int] = Field(None, ge=1900, le=2100)


@router.post(
    "/{tese_id}/evidencias/coletar",
    status_code=202,
    dependencies=[Depends(rate_limit("teses_evidencia_coletar", 3))],
)
async def coletar_evidencia(
    tese_id: str,
    req: ColetarEvidenciaRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Dispara a coleta de evidência jurídica em background p/ a tese e
    devolve job_id p/ polling."""
    if not _pode_editar(cu):
        raise HTTPException(403)
    await _tese_ou_404(db, tese_id)

    fonte = req.fonte.strip().lower()
    info = FONTES.get(fonte)
    if not info or not info["enabled"]:
        raise HTTPException(
            status_code=422,
            detail=f"Fonte '{req.fonte}' indisponível. Fontes: "
                   f"{', '.join(k for k, v in FONTES.items() if v['enabled'])}.",
        )
    job_id = str(uuid4())
    background_tasks.add_task(
        executar_coleta_evidencia, job_id, tese_id, fonte, req.consulta.strip(),
        (req.tribunal or "").strip() or None, req.limite,
        cu.id, getattr(cu.role, "value", str(cu.role)),
        ano=req.ano,
    )
    return {
        "job_id": job_id,
        "status": "executando",
        "tese_id": tese_id,
        "fonte": fonte,
        "detail": "Coleta iniciada em segundo plano. Acompanhe em "
                  f"/teses/{tese_id}/evidencias/coletar/status/{job_id}.",
    }


@router.get(
    "/{tese_id}/evidencias/coletar/status/{job_id}",
    dependencies=[Depends(rate_limit("teses_evidencia_coletar_status", 30))],
)
async def status_coleta_evidencia(
    tese_id: str,
    job_id: str,
    cu: User = Depends(get_current_user),
):
    """Status do job (executando | concluido | erro) com o resumo da coleta.

    Ownership: só o usuário que disparou o job (ou superadmin/admin) enxerga o
    status — job alheio responde o MESMO 404 de job inexistente."""
    st = status_job(job_id)
    role = getattr(cu.role, "value", str(cu.role))
    dono = st is not None and st.get("user_id") == cu.id
    if st is None or st.get("tese_id") != tese_id or not (dono or role in ("superadmin", "admin")):
        raise HTTPException(
            status_code=404,
            detail="Job não encontrado (expirado ou id inválido). O resultado "
                   "durável fica em fontes_ingestao/audit_logs.",
        )
    return st
