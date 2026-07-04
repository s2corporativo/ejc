from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.core.veredito_ia import VereditoIA
from app.models.user import User
from app.schemas.veredito_ia_schema import AnaliseTeseRequest, AnaliseTeseResponse

router = APIRouter()


@router.post("/veredito_ia/analisar", response_model=AnaliseTeseResponse,
             dependencies=[Depends(rate_limit("veredito-ia", 10))])
async def analisar_tese(
    request: AnaliseTeseRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Veredito IA — probabilidade por jurimetria REAL + jurisprudência do RAG.

    Auditoria 04/07/2026: endpoint deixou de ser simulação; agora exige
    autenticação, registra AILog e respeita o escopo de cliente do caso.
    Toda saída é RASCUNHO (HITL) — ver campo `avisos` da resposta.
    """
    if request.case_id:
        await verificar_acesso_caso(db, cu, request.case_id)
    return await VereditoIA().predict_success(
        request.tese_juridica,
        request.area_juridica,
        request.tribunais_selecionados,
        db=db,
        user=cu,
        case_id=request.case_id,
    )
