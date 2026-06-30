"""
Cérebro do EJC — Módulo Único de Inteligência Jurídica Estratégica.
Centraliza IA, Banco de Teses, Jurisprudência, Legislação e Conhecimento Interno.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.core.skill_router import skill_router
from app.core.ai_brain import ai_brain
import json

router = APIRouter(prefix="/cerebro", tags=["Cérebro"])

@router.get("/status")
async def status_cerebro(cu: User = Depends(get_current_user)):
    return {"status": "online", "version": "3.0", "mode": "soberania_tecnologica"}

@router.post("/analise-estrategica")
async def analise_estrategica(payload: dict, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    """
    Executa análise estratégica unificada com roteamento automático de Skills.
    """
    texto_caso = payload.get("texto", "")
    ramo = skill_router.identificar_ramo(texto_caso)
    instrucao_skill = skill_router.get_skill_instruction(ramo)
    
    # Executa análise via Modo Duas IAs com a instrução da Skill específica
    contexto_completo = f"{instrucao_skill}\n\nContexto do Caso: {texto_caso}"
    resultado = await ai_brain.modo_duas_ias(contexto_completo)
    
    return {
        "ramo_identificado": ramo,
        "skill_acionada": instrucao_skill,
        "analise": resultado
    }

@router.get("/teses")
async def listar_teses(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    result = await db.execute(text("SELECT * FROM teses WHERE deleted_at IS NULL ORDER BY taxa_sucesso DESC"))
    return result.mappings().all()

@router.post("/jurisprudencia/pesquisa")
async def pesquisar_jurisprudencia(query: str, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    # Simulação de busca semântica integrada
    return {"query": query, "resultados": []}
