"""
Router de Diplomacia Digital — EJC v3.0
Estratégia de Acordos e Liquidez Judicial.
"""
from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.models.user import User
from app.services.diplomacia_digital import diplomacia
from app.services.sentimento_magistrado import sentimento_ia

router = APIRouter(prefix="/diplomacia-v3", tags=["Diplomacia"])

@router.post("/calcular-acordo")
async def calcular_acordo(payload: dict, cu: User = Depends(get_current_user)):
    valor = payload.get("valor_causa")
    prob = payload.get("prob_exito")
    tempo = payload.get("tempo_anos")
    
    if not all([valor, prob, tempo]):
        raise HTTPException(400, "Dados insuficientes para cálculo.")
        
    return diplomacia.calcular_ponto_equilibrio(valor, prob, tempo)

@router.post("/analisar-magistrado")
async def analisar_magistrado(payload: dict, cu: User = Depends(get_current_user)):
    decisoes = payload.get("decisoes", [])
    return await sentimento_ia.analisar_tendencia(decisoes)
