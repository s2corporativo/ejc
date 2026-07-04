"""
Router EJC Intelligence — Radar de Poder v3.0
Monitoramento dos Três Poderes e Antecipação Estratégica.
"""
from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.models.user import User
from app.services.radar_poder import radar_poder
from app.core.ai_brain import ai_brain

router = APIRouter(prefix="/intelligence-v3", tags=["Intelligence"])

@router.get("/radar/legislativo")
async def radar_legislativo(cu: User = Depends(get_current_user)):
    keywords = ["tributo", "pis", "cofins", "medicamento", "veterinario", "licitacao"]
    alertas = await radar_poder.monitorar_projetos_lei(keywords)
    return {"alertas_legislativos": alertas}

@router.post("/analise-impacto")
async def analise_impacto(payload: dict, cu: User = Depends(get_current_user)):
    texto_noticia = payload.get("texto")
    prompt = f"""
    Como especialista em Inteligência Política, analise este fato e gere um Resumo Executivo de Impacto:
    Fato: {texto_noticia}
    
    Estrutura:
    1. O que mudou?
    2. Qual o impacto imediato para empresas e advogados?
    3. Qual a ação recomendada para o Dr. Clovis?
    """
    analise = await ai_brain.generate(prompt, "principal")
    return {"resumo_executivo": analise}
