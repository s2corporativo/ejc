"""
deep_research.py — Deep Research jurídica (pesquisa multi-etapa em background).

POST /deep-research/iniciar → cria job (status em_andamento) + dispara worker via
BackgroundTasks; responde job_id imediatamente.
GET  /deep-research/{job_id} → status/progresso/etapas/resultado (ownership: dono
ou gestão).

Sem Celery/Redis: o worker roda em fastapi.BackgroundTasks e grava o andamento no
job persistido (o cliente faz polling). Todo resultado é RASCUNHO (HITL/OAB).
"""
from __future__ import annotations
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.deep_research import DeepResearchJob
from app.models.user import User
from app.services import deep_research_service

router = APIRouter(prefix="/deep-research", tags=["Deep Research Jurídica"])


class IniciarReq(BaseModel):
    pergunta: str = Field(..., min_length=10, max_length=8000,
                          description="Questão jurídica a pesquisar")
    tese: str | None = Field(None, max_length=8000,
                             description="Tese a investigar (opcional)")
    case_id: str | None = Field(None, description="Caso vinculado (opcional)")
    nivel_inteligencia: str = Field("alto", pattern="^(padrao|alto|maximo)$")


def _serializar(job: DeepResearchJob) -> dict:
    return {
        "id": job.id,
        "status": job.status.value if hasattr(job.status, "value") else job.status,
        "progresso": job.progresso,
        "etapa_atual": job.etapa_atual,
        "pergunta": job.pergunta,
        "tese": job.tese,
        "case_id": job.case_id,
        "nivel_inteligencia": job.nivel_inteligencia,
        "total_subquestoes": job.total_subquestoes,
        "total_chamadas_ia": job.total_chamadas_ia,
        "etapas": json.loads(job.etapas_json) if job.etapas_json else [],
        "resultado": json.loads(job.resultado_json) if job.resultado_json else None,
        "erro_mensagem": job.erro_mensagem,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "concluido_em": job.concluido_em.isoformat() if job.concluido_em else None,
    }


@router.post("/iniciar", status_code=202,
             dependencies=[Depends(rate_limit("deep_research", 3))])
async def iniciar(req: IniciarReq, background: BackgroundTasks,
                  db: AsyncSession = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    """Cria o job e dispara o worker. Responde job_id imediatamente (polling no GET)."""
    if req.case_id:
        # Gate de ownership do caso (404/403). Reaproveita a mesma regra dos demais.
        await verificar_acesso_caso(db, cu, req.case_id)

    job = await deep_research_service.criar_job(
        db, user_id=cu.id, pergunta=req.pergunta, tese=req.tese,
        case_id=req.case_id, nivel_inteligencia=req.nivel_inteligencia,
    )
    background.add_task(deep_research_service.executar_deep_research, job.id)
    return {"job_id": job.id, "status": job.status.value, "progresso": job.progresso}


@router.get("/{job_id}")
async def obter(job_id: str, db: AsyncSession = Depends(get_db),
                cu: User = Depends(get_current_user)):
    """Status/progresso/resultado do job. Só o dono ou a gestão (socio+) enxerga."""
    job = await db.get(DeepResearchJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Pesquisa não encontrada")
    if job.user_id != cu.id and not is_gestao(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para esta pesquisa")
    return _serializar(job)
