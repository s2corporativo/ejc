import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.core.veredito_ia import VereditoIA
from app.models.user import User
from app.schemas.veredito_ia_schema import AnaliseTeseRequest, AnaliseTeseResponse

logger = logging.getLogger("ejc.veredito_ia")

router = APIRouter()


@router.post("/veredito_ia/analisar", response_model=AnaliseTeseResponse)
async def analisar_tese(
    request: AnaliseTeseRequest,
    veredito_ia: VereditoIA = Depends(VereditoIA),
    cu: User = Depends(get_current_user),
):
    # Expõe jurimetria real do escritório + trechos da base interna — exige JWT.
    try:
        return await veredito_ia.predict_success(
            request.tese_juridica,
            request.area_juridica,
            request.tribunais_selecionados,
        )
    except Exception as e:
        logger.exception("Falha em veredito_ia.analisar")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Falha ao gerar a análise de veredito. Tente novamente.",
        ) from e
