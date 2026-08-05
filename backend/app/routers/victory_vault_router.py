from fastapi import APIRouter, Depends, status
from typing import List
from app.schemas.victory_vault_schema import TeseVitoriosaCreate, TeseVitoriosa, ModeloDocumentoCreate, ModeloDocumento
from app.core.victory_vault import VictoryVault
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, requer_advogado
from app.models.user import User

# P1-1: todas as rotas exigem JWT (antes eram públicas via auth_middleware).
router = APIRouter(dependencies=[Depends(get_current_user)])


def _req_advogado(cu: User = Depends(get_current_user)) -> User:
    """ESCRITA no cofre institucional exige advogado+.

    P1 da auditoria integral (docs/auditoria-ejc/08-backend.md §6.3): as rotas
    de criação gravavam tese e modelo no acervo do escritório apenas com JWT —
    qualquer perfil interno, inclusive secretaria (nível 2) e estagiário (3).
    Tese vitoriosa e modelo de documento são conteúdo que volta a ser reusado em
    peça, logo é ato jurídico. A LEITURA segue aberta a staff, por desenho.
    """
    requer_advogado(cu)
    return cu

@router.post("/victory_vault/teses", dependencies=[Depends(rate_limit("victory-vault-tese", 20))], response_model=TeseVitoriosa, status_code=status.HTTP_201_CREATED)
async def create_tese_vitoriosa(tese: TeseVitoriosaCreate, cu: User = Depends(_req_advogado), victory_vault: VictoryVault = Depends(VictoryVault)):
    return await victory_vault.create_tese_vitoriosa(tese)

@router.get("/victory_vault/teses", response_model=List[TeseVitoriosa])
async def get_teses_vitoriosas(area_juridica: str = None, query: str = None, victory_vault: VictoryVault = Depends(VictoryVault)):
    return await victory_vault.get_teses_vitoriosas(area_juridica=area_juridica, query=query)

@router.post("/victory_vault/modelos", dependencies=[Depends(rate_limit("victory-vault-modelo", 20))], response_model=ModeloDocumento, status_code=status.HTTP_201_CREATED)
async def create_modelo_documento(modelo: ModeloDocumentoCreate, cu: User = Depends(_req_advogado), victory_vault: VictoryVault = Depends(VictoryVault)):
    return await victory_vault.create_modelo_documento(modelo)

@router.get("/victory_vault/modelos", response_model=List[ModeloDocumento])
async def get_modelos_documentos(tipo_documento: str = None, area_juridica: str = None, query: str = None, victory_vault: VictoryVault = Depends(VictoryVault)):
    return await victory_vault.get_modelos_documentos(tipo_documento=tipo_documento, area_juridica=area_juridica, query=query)
