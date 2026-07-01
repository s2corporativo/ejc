from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.victory_vault_schema import TeseVitoriosaCreate, TeseVitoriosa, ModeloDocumentoCreate, ModeloDocumento
from app.core.victory_vault import VictoryVault
from app.core.security import get_current_user

# P1-1: todas as rotas exigem JWT (antes eram públicas via auth_middleware).
router = APIRouter(dependencies=[Depends(get_current_user)])

@router.post("/victory_vault/teses", response_model=TeseVitoriosa, status_code=status.HTTP_201_CREATED)
async def create_tese_vitoriosa(tese: TeseVitoriosaCreate, victory_vault: VictoryVault = Depends(VictoryVault)):
    return await victory_vault.create_tese_vitoriosa(tese)

@router.get("/victory_vault/teses", response_model=List[TeseVitoriosa])
async def get_teses_vitoriosas(area_juridica: str = None, query: str = None, victory_vault: VictoryVault = Depends(VictoryVault)):
    return await victory_vault.get_teses_vitoriosas(area_juridica=area_juridica, query=query)

@router.post("/victory_vault/modelos", response_model=ModeloDocumento, status_code=status.HTTP_201_CREATED)
async def create_modelo_documento(modelo: ModeloDocumentoCreate, victory_vault: VictoryVault = Depends(VictoryVault)):
    return await victory_vault.create_modelo_documento(modelo)

@router.get("/victory_vault/modelos", response_model=List[ModeloDocumento])
async def get_modelos_documentos(tipo_documento: str = None, area_juridica: str = None, query: str = None, victory_vault: VictoryVault = Depends(VictoryVault)):
    return await victory_vault.get_modelos_documentos(tipo_documento=tipo_documento, area_juridica=area_juridica, query=query)
