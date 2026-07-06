"""
Módulo de Biblioteca de Prompts Jurídicos (Seção 4.154).
Permite criar, editar, versionar e executar prompts com um clique.
"""
from uuid import uuid4
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import Column, String, Text, DateTime, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.models.prompt_juridico import PromptJuridico
from app.core.security import get_current_user
from app.models.user import User

# Model ORM


# Schemas
class PromptCreate(BaseModel):
    titulo: str
    categoria: str
    conteudo: str

class PromptResponse(PromptCreate):
    id: str

router = APIRouter(prefix="/prompts-biblioteca", tags=["Prompts Jurídicos"])

@router.post("/", response_model=PromptResponse, status_code=201)
async def criar_prompt(payload: PromptCreate, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    p = PromptJuridico(id=str(uuid4()), created_by=cu.id, **payload.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p

@router.get("/", response_model=List[PromptResponse])
async def listar_prompts(categoria: Optional[str] = None, db: AsyncSession = Depends(get_db),
                         cu: User = Depends(get_current_user)):
    q = select(PromptJuridico)
    if categoria:
        q = q.where(PromptJuridico.categoria == categoria)
    res = await db.execute(q)
    return res.scalars().all()

@router.post("/{prompt_id}/executar")
async def executar_prompt(
    prompt_id: str, 
    contexto: str = Body(..., embed=True), 
    db: AsyncSession = Depends(get_db), 
    cu: User = Depends(get_current_user)
):
    # Consolidado no NÚCLEO ÚNICO de IA: sanitização LGPD (abort em PII
    # residual), policy de provider, validação da resposta, HITL e AILog.
    from app.services.ai.core.orchestrator import orchestrator

    p = await db.get(PromptJuridico, prompt_id)
    if not p:
        raise HTTPException(status_code=404, detail="Prompt não encontrado")

    full_prompt = f"{p.conteudo}\n\nCONTEXTO:\n{contexto}"
    res = await orchestrator.run(
        db=db,
        user=cu,
        task_type="chat",
        domain=None,
        mensagem=full_prompt,
        usar_rag=False,
    )

    # Shape legado preservado ({modelo_utilizado, tipo_demanda, resposta, status})
    # + campos do núcleo acrescentados (log_id, aviso_hitl, is_rascunho).
    return {
        "modelo_utilizado": res.get("modelo"),
        "tipo_demanda": str(getattr(p.categoria, "value", p.categoria) or "").lower(),
        "resposta": res.get("conteudo"),
        "status": "sucesso",
        "log_id": res.get("log_id"),
        "is_rascunho": res.get("is_rascunho", True),
        "aviso_hitl": res.get("aviso_hitl"),
    }
