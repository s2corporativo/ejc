from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.veredito_ia_schema import AnaliseTeseRequest, AnaliseTeseResponse
from app.core.veredito_ia import VereditoIA

router = APIRouter()

@router.post("/veredito_ia/analisar", response_model=AnaliseTeseResponse)
async def analisar_tese(request: AnaliseTeseRequest, veredito_ia: VereditoIA = Depends(VereditoIA)):
    try:
        return await veredito_ia.predict_success(request.tese_juridica, request.area_juridica, request.tribunais_selecionados)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
