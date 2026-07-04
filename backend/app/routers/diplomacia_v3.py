"""
Router de Diplomacia Digital — EJC v3.0
Estratégia de Acordos e Liquidez Judicial.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.models.user import User
from app.services.diplomacia_digital import diplomacia
from app.services.sentimento_magistrado import sentimento_ia

router = APIRouter(prefix="/diplomacia-v3", tags=["Diplomacia"])


class AcordoRequest(BaseModel):
    valor_causa: float = Field(gt=0, le=1e12)
    prob_exito: float = Field(ge=0, le=1)
    tempo_anos: float = Field(gt=0, le=50)


@router.post("/calcular-acordo")
async def calcular_acordo(req: AcordoRequest, cu: User = Depends(get_current_user)):
    return diplomacia.calcular_ponto_equilibrio(req.valor_causa, req.prob_exito, req.tempo_anos)


@router.post("/dossie-pressao")
async def dossie_pressao(req: AcordoRequest, cu: User = Depends(get_current_user)):
    """Calcula o ponto de equilíbrio e gera o Dossiê de Pressão via IA."""
    dados = diplomacia.calcular_ponto_equilibrio(req.valor_causa, req.prob_exito, req.tempo_anos)
    resultado = await diplomacia.gerar_dossie_pressao(dados)
    if resultado.get("status") == "erro":
        raise HTTPException(502, resultado.get("mensagem", "Falha na geração do dossiê."))
    return resultado

@router.post("/analisar-magistrado")
async def analisar_magistrado(payload: dict, cu: User = Depends(get_current_user)):
    decisoes = payload.get("decisoes", [])
    return await sentimento_ia.analisar_tendencia(decisoes)
