"""
Portal de Mediação Digital EJC v5.0.
Ambiente de negociação guiada pelo Algoritmo de Ponto de Equilíbrio.
"""
from fastapi import APIRouter
from app.services.diplomacia_digital import diplomacia

router = APIRouter(prefix="/mediacao", tags=["Mediacao"])

@router.get("/proposta/{caso_id}")
async def obter_proposta_mediacao(caso_id: str):
    # Recupera o Ponto de Equilíbrio calculado
    proposta = diplomacia.calcular_ponto_equilibrio(valor_causa=100000, prob_exito=0.85, tempo_anos=3.2)
    return {
        "valor_sugerido": proposta["valor_vpl"],
        "justificativa_visual_law": "Com base na probabilidade de êxito de 85% e tempo de tramitação de 3.2 anos.",
        "status": "aguardando_contraparte"
    }

@router.post("/aceitar/{caso_id}")
async def aceitar_acordo(caso_id: str):
    return {"status": "acordo_concluido", "proximo_passo": "gerar_termo_acordo"}
