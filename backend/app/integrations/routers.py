# ── app/integrations/routers.py ──────────────────────────────────────────────
# Routers das integrações externas públicas (/api/integracoes/*).
#
# Segurança (auditoria 2026-07-18):
#   • TODOS os endpoints exigem JWT (get_current_user), além do AuthMiddleware
#     global — sem isso o backend viraria proxy aberto para consultas de
#     CNPJ/intimações (dados de terceiros — LGPD) e queimaria a cota da API
#     key pública do DataJud.
#   • Rate limit individual (padrão do repo, ex. search.py) — protege a cota
#     das APIs públicas contra loop de usuário autenticado/token vazado.
#   • Consultas que tocam dados de terceiros (DJEN por OAB/processo, CNPJ)
#     geram trilha em audit_logs (LGPD art. 6º, X — padrão criar_audit_log).
#   • O detail do 502 é GENÉRICO; o corpo de erro do upstream vai só para o
#     log do servidor (padrão main.py: nunca repassar detalhe interno).
#   • Timeouts/falhas de conexão httpx também viram 502 (não 500 genérico).
#
# DECISÃO explícita: o endpoint cru do DataJud NÃO obedece ao kill-switch
# DATAJUD_ENABLED — esse flag governa a integração INTERNA (sync de
# andamentos/prazos via datajud_service). Aqui a consulta é manual, autenticada
# e auditada, e funciona out-of-the-box com a chave pública do CNJ
# (settings.DATAJUD_API_KEY, se configurada, tem precedência sobre o fallback).
#
# O router do Conecta gov.br NÃO existe aqui de propósito: integração pendente
# de credenciamento institucional (ver conecta_gov_client.py) — só ganha
# endpoint quando CONECTA_CLIENT_ID/CONECTA_CLIENT_SECRET existirem de verdade.
# SEM `from __future__ import annotations`: o wrapper do slowapi faz o FastAPI
# resolver anotações string fora deste módulo → Optional[date] quebraria.
import logging
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.services.datajud_service import _SEG_TR_ALIAS

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

logger = logging.getLogger("ejc.integracoes")

datajud_router = APIRouter(prefix="/integracoes/datajud", tags=["integracoes"])
djen_router = APIRouter(prefix="/integracoes/djen", tags=["integracoes"])
brasilapi_router = APIRouter(prefix="/integracoes/brasilapi", tags=["integracoes"])

# settings.DATAJUD_API_KEY (pydantic lê o .env mesmo fora do Docker) tem
# precedência; vazia → cadeia de fallback do cliente (env → chave pública CNJ).
_datajud = DataJudClient(api_key=get_settings().DATAJUD_API_KEY or None)
_djen = DjenComunicaClient()
_brasilapi = BrasilApiClient()

# Review Codex (PR #305): os 5 aliases de TRIBUNAL_ALIASES cobriam uma fração
# dos tribunais. Completa o mapa sigla → alias a partir do mapeamento auditado
# do serviço interno (Res. CNJ 65/2008 — todos os TJs, TRTs, TRFs, STJ e TST);
# o alias embute a própria sigla ("api_publica_tjmg" → "TJMG"). As entradas da
# spec (TRIBUNAL_ALIASES) têm precedência.
_ALIAS_POR_SIGLA: dict = {
    alias.removeprefix("api_publica_").upper(): alias
    for alias in _SEG_TR_ALIAS.values()
}
_ALIAS_POR_SIGLA.update(TRIBUNAL_ALIASES)

# Erros de integração mapeados para 502 com detail genérico (o detalhe do
# upstream fica no log). ValueError cobre 200 com corpo não-JSON (WAF/
# manutenção); httpx.HTTPError cobre timeout/conexão/transport.
_ERROS_UPSTREAM = (
    DataJudError, DjenComunicaError, BrasilApiError, ValueError, httpx.HTTPError,
)


def _falha_upstream(origem: str, exc: Exception) -> HTTPException:
    logger.warning("Integração %s falhou: %s: %s",
                   origem, type(exc).__name__, str(exc)[:500])
    return HTTPException(502, f"Falha na consulta à API externa ({origem}).")


def _somente_digitos(valor: str, tamanho: int, campo: str) -> str:
    limpo = "".join(ch for ch in valor if ch.isdigit())
    if len(limpo) != tamanho:
        raise HTTPException(
            400, f"{campo} inválido: esperado {tamanho} dígitos (com ou sem máscara)."
        )
    return limpo


async def _auditar_consulta(
    db: AsyncSession, cu: User, entidade: str, registro_id: str,
) -> None:
    await criar_audit_log(
        db, cu.id, getattr(cu.role, "value", str(cu.role)),
        "CONSULTA_EXTERNA", entidade, registro_id,
    )
    await db.commit()


@datajud_router.get("/processos/{tribunal}/{numero_processo}")
@limiter.limit("30/minute")
async def consultar_processo_datajud(
    request: Request,
    tribunal: str,
    numero_processo: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alias = _ALIAS_POR_SIGLA.get(tribunal.upper())
    if not alias:
        raise HTTPException(
            400,
            f"Tribunal '{tribunal}' não mapeado — use a sigla oficial "
            "(ex.: TJMG, TJSP, TRT3, TRF1, STJ, TST).",
        )
    numero = _somente_digitos(numero_processo, 20, "Número de processo (CNJ)")
    try:
        resultado = await _datajud.consultar_processo(numero, alias)
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("DataJud", exc)
    await _auditar_consulta(db, current_user, "integracoes_datajud", numero)
    return resultado


@djen_router.get("/oab/{uf}/{numero_oab}")
@limiter.limit("30/minute")
async def consultar_djen_por_oab(
    request: Request,
    uf: str = Path(pattern=r"^[A-Za-z]{2}$"),
    numero_oab: str = Path(pattern=r"^\d{1,10}$"),
    data_inicio: Optional[date] = Query(None, description="dataDisponibilizacaoInicio"),
    data_fim: Optional[date] = Query(None, description="dataDisponibilizacaoFim"),
    pagina: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        resultado = await _djen.consultar_por_oab(
            numero_oab, uf.upper(),
            data_inicio=data_inicio, data_fim=data_fim, pagina=pagina,
        )
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("DJEN/Comunica", exc)
    await _auditar_consulta(
        db, current_user, "integracoes_djen", f"OAB {numero_oab}/{uf.upper()}"
    )
    return resultado


@djen_router.get("/processos/{numero_processo}")
@limiter.limit("30/minute")
async def consultar_djen_por_processo(
    request: Request,
    numero_processo: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    numero = _somente_digitos(numero_processo, 20, "Número de processo (CNJ)")
    try:
        resultado = await _djen.consultar_por_processo(numero)
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("DJEN/Comunica", exc)
    await _auditar_consulta(db, current_user, "integracoes_djen", numero)
    return resultado


@brasilapi_router.get("/cnpj/{cnpj}")
@limiter.limit("30/minute")
async def consultar_cnpj(
    request: Request,
    cnpj: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    numero = _somente_digitos(cnpj, 14, "CNPJ")
    try:
        resultado = await _brasilapi.consultar_cnpj(numero)
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("BrasilAPI/CNPJ", exc)
    await _auditar_consulta(db, current_user, "integracoes_cnpj", numero)
    return resultado


@brasilapi_router.get("/cep/{cep}")
@limiter.limit("30/minute")
async def consultar_cep(
    request: Request,
    cep: str,
    current_user: User = Depends(get_current_user),
):
    # CEP é dado de endereço público, não identifica pessoa — sem audit log.
    numero = _somente_digitos(cep, 8, "CEP")
    try:
        return await _brasilapi.consultar_cep(numero)
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("BrasilAPI/CEP", exc)
