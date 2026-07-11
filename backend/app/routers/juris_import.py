# ── app/routers/juris_import.py ──────────────────────────────────────────────
# Importação de jurisprudência via APIs oficiais (página Conhecimento).
#
#   POST /conhecimento/importar-jurisprudencia            (advogado+, 3/min)
#        → dispara job em BackgroundTasks; resposta 202 com job_id.
#   GET  /conhecimento/importar-jurisprudencia/fontes     (autenticado)
#        → fontes disponíveis + última execução (fontes_ingestao).
#   GET  /conhecimento/importar-jurisprudencia/status/{job_id}
#        → status consultável do job ({importados, duplicados, erros}).
#
# A importação é determinística (sem IA externa); trilha em audit_logs e
# fontes_ingestao — ver services/juris_import/ingest.py.
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles
from app.models.rag import FonteIngestao
from app.models.user import User
from app.services.juris_import import FONTES, fontes_disponiveis
from app.services.juris_import.ingest import executar_importacao, status_job

router = APIRouter(prefix="/conhecimento", tags=["Conhecimento — Importar Jurisprudência"])

# Gate advogado+ (hierárquico: advogado_auxiliar e abaixo → 403).
_GATE_ADVOGADO = ["superadmin", "admin", "socio", "advogado"]


class ImportarJurisRequest(BaseModel):
    fonte: str = Field(..., max_length=30)
    consulta: str = Field(..., min_length=3, max_length=300)
    tribunal: Optional[str] = Field(None, max_length=20)
    limite: int = Field(20, ge=1, le=100)


@router.post(
    "/importar-jurisprudencia",
    status_code=202,
    dependencies=[Depends(rate_limit("juris_import", 3))],
)
async def importar_jurisprudencia(
    req: ImportarJurisRequest,
    background_tasks: BackgroundTasks,
    cu: User = Depends(require_roles(_GATE_ADVOGADO)),
):
    """Dispara a importação em background e devolve job_id p/ polling."""
    fonte = req.fonte.strip().lower()
    info = FONTES.get(fonte)
    if not info or not info["enabled"]:
        raise HTTPException(
            status_code=422,
            detail=f"Fonte '{req.fonte}' indisponível. Consulte GET "
                   "/conhecimento/importar-jurisprudencia/fontes.",
        )
    job_id = str(uuid4())
    background_tasks.add_task(
        executar_importacao, job_id, fonte, req.consulta.strip(),
        (req.tribunal or "").strip() or None, req.limite,
        cu.id, getattr(cu.role, "value", str(cu.role)),
    )
    return {
        "job_id": job_id,
        "status": "executando",
        "fonte": fonte,
        "detail": "Importação iniciada em segundo plano. Acompanhe em "
                  f"/conhecimento/importar-jurisprudencia/status/{job_id}.",
    }


@router.get("/importar-jurisprudencia/fontes")
async def listar_fontes(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Fontes de importação disponíveis + frescor da última execução."""
    fontes = fontes_disponiveis()
    slugs = [f"juris_import_{f['slug']}" for f in fontes]
    rows = (await db.execute(
        select(FonteIngestao).where(FonteIngestao.slug.in_(slugs))
    )).scalars().all()
    por_slug = {r.slug: r for r in rows}
    for f in fontes:
        r = por_slug.get(f"juris_import_{f['slug']}")
        f["ultima_execucao"] = r.ultima_execucao if r else None
        f["ultimo_status"] = r.ultimo_status if r else None
        f["registros_novos"] = r.registros_novos if r else 0
    return {"fontes": fontes}


@router.get("/importar-jurisprudencia/status/{job_id}")
async def status_importacao(
    job_id: str,
    cu: User = Depends(get_current_user),
):
    """Status do job (executando | concluido | erro) com o resumo da carga."""
    st = status_job(job_id)
    if st is None:
        raise HTTPException(
            status_code=404,
            detail="Job não encontrado (expirado ou id inválido). O resultado "
                   "durável fica em fontes_ingestao/audit_logs.",
        )
    return st
