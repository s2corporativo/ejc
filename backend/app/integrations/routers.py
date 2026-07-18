# ── app/integrations/routers.py ──────────────────────────────────────────────
# Routers das integrações externas públicas (/api/integracoes/*).
#
# Segurança: TODOS os endpoints exigem JWT (get_current_user), seguindo o
# padrão dos demais routers do EJC — além da proteção do AuthMiddleware
# global. Sem isso o backend viraria um proxy aberto para consultas de
# CNPJ/intimações (dados de terceiros — LGPD) e consumiria a cota da API
# key do DataJud para qualquer anônimo.
#
# O router do Conecta gov.br NÃO existe aqui de propósito: a integração está
# pendente de credenciamento institucional (ver conecta_gov_client.py) e só
# deve ganhar endpoint quando CONECTA_CLIENT_ID/CONECTA_CLIENT_SECRET
# existirem de verdade.
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user

from app.integrations.brasilapi_client import BrasilApiClient, BrasilApiError
from app.integrations.datajud_client import (
    TRIBUNAL_ALIASES,
    DataJudClient,
    DataJudError,
)
from app.integrations.djen_comunica_client import (
    DjenComunicaClient,
    DjenComunicaError,
)

datajud_router = APIRouter(prefix="/integracoes/datajud", tags=["integracoes"])
djen_router = APIRouter(prefix="/integracoes/djen", tags=["integracoes"])
brasilapi_router = APIRouter(prefix="/integracoes/brasilapi", tags=["integracoes"])

_datajud = DataJudClient()
_djen = DjenComunicaClient()
_brasilapi = BrasilApiClient()


@datajud_router.get("/processos/{tribunal}/{numero_processo}")
async def consultar_processo_datajud(
    tribunal: str,
    numero_processo: str,
    current_user=Depends(get_current_user),
):
    alias = TRIBUNAL_ALIASES.get(tribunal.upper())
    if not alias:
        raise HTTPException(
            400, f"Tribunal '{tribunal}' não mapeado em TRIBUNAL_ALIASES"
        )
    try:
        return await _datajud.consultar_processo(numero_processo, alias)
    except DataJudError as exc:
        raise HTTPException(502, str(exc))


@djen_router.get("/oab/{uf}/{numero_oab}")
async def consultar_djen_por_oab(
    uf: str,
    numero_oab: str,
    current_user=Depends(get_current_user),
):
    try:
        return await _djen.consultar_por_oab(numero_oab, uf)
    except DjenComunicaError as exc:
        raise HTTPException(502, str(exc))


@djen_router.get("/processos/{numero_processo}")
async def consultar_djen_por_processo(
    numero_processo: str,
    current_user=Depends(get_current_user),
):
    try:
        return await _djen.consultar_por_processo(numero_processo)
    except DjenComunicaError as exc:
        raise HTTPException(502, str(exc))


@brasilapi_router.get("/cnpj/{cnpj}")
async def consultar_cnpj(cnpj: str, current_user=Depends(get_current_user)):
    try:
        return await _brasilapi.consultar_cnpj(cnpj)
    except BrasilApiError as exc:
        raise HTTPException(502, str(exc))


@brasilapi_router.get("/cep/{cep}")
async def consultar_cep(cep: str, current_user=Depends(get_current_user)):
    try:
        return await _brasilapi.consultar_cep(cep)
    except BrasilApiError as exc:
        raise HTTPException(502, str(exc))
