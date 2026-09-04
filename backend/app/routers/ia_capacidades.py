# ── app/routers/ia_capacidades.py ────────────────────────────────────────────
# PORTA CANÔNICA DE IA DO EJC — uma rota por CAPACIDADE (item I1 da análise E2E
# de 03/09/2026):
#
#   POST /ia/analisar   POST /ia/redigir   POST /ia/resumir
#   POST /ia/conversar  POST /ia/extrair
#
# Todas resolvem em `services/ai/core/capacidades.py` → `SingleAICoreOrchestrator`
# (sigilo do caso, escopo cliente+caso, RAG, nível por tarefa, gate de citações,
# HITL e AILog). As portas antigas de `/ai/*` e `/ia-especializada/*` continuam
# atendendo por compatibilidade e apontam para cá.
#
# Nenhuma rota aqui é pública: `get_current_user` + bloqueio de `cliente_externo`
# em todas; `requer_equipe_juridica` nas que produzem conteúdo jurídico
# (analisar/redigir); ownership do caso quando vem `case_id`.
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_errors import http_erro_ia
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, requer_equipe_juridica
from app.models.user import User
from app.schemas.ai import (
    AnalisarRequest, ConversarRequest, ExtrairRequest, RedigirRequest,
    RespostaCapacidadeIA, ResumirRequest,
)
from app.services.ai.core import capacidades

router = APIRouter(prefix="/ia", tags=["IA — Capacidades"])


def _bloquear_cliente_externo(cu: User) -> None:
    """`UserRole` é `(str, Enum)` sem `__str__`: `str(role)` devolve
    "UserRole.cliente_externo" e o gate nunca dispara. Compara pelo VALOR."""
    role = getattr(cu, "role", "")
    if getattr(role, "value", role) == "cliente_externo":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Funções de IA internas não estão disponíveis no portal do cliente.",
        )


def _kill_switch() -> None:
    if not bool(get_settings().AI_ENABLED):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "IA desabilitada")


async def _porta(
    capacidade: str, body, db: AsyncSession, cu: User, *, exige_equipe: bool = False,
) -> dict:
    _bloquear_cliente_externo(cu)
    if exige_equipe:
        requer_equipe_juridica(
            cu, "Esta capacidade de IA é restrita à equipe jurídica.",
        )
    _kill_switch()
    # O orquestrador revalida o acesso ao caso; o gate explícito aqui garante
    # 403 ANTES de qualquer montagem de contexto/dossiê (mesma regra das portas
    # antigas — auditoria de IDOR de 18/08).
    if body.case_id:
        from app.core.ownership import verificar_acesso_caso
        await verificar_acesso_caso(db, cu, body.case_id)
    try:
        return await capacidades.PORTAS[capacidade](
            db, cu,
            case_id=body.case_id,
            texto=body.texto,
            mensagem=body.mensagem,
            area=body.area,
            perfil=body.perfil,
            opcoes=body.opcoes,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise http_erro_ia(e, status.HTTP_502_BAD_GATEWAY, contexto=f"ia/{capacidade}")


@router.post("/analisar", response_model=RespostaCapacidadeIA,
             dependencies=[Depends(rate_limit("ia-cap-analisar", 15))])
async def analisar(
    body: AnalisarRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Análise jurídica de fatos/caso — teses, riscos e estratégia (rascunho)."""
    return await _porta("analisar", body, db, cu, exige_equipe=True)


@router.post("/redigir", response_model=RespostaCapacidadeIA,
             dependencies=[Depends(rate_limit("ia-cap-redigir", 10))])
async def redigir(
    body: RedigirRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Redação de peça/minuta/comunicação — SEMPRE rascunho sob revisão (OAB)."""
    return await _porta("redigir", body, db, cu, exige_equipe=True)


@router.post("/resumir", response_model=RespostaCapacidadeIA,
             dependencies=[Depends(rate_limit("ia-cap-resumir", 15))])
async def resumir(
    body: ResumirRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Resumo objetivo de texto/documento, sem acrescentar fato que não esteja lá."""
    return await _porta("resumir", body, db, cu)


@router.post("/conversar", response_model=RespostaCapacidadeIA,
             dependencies=[Depends(rate_limit("ia-cap-conversar", 20))])
async def conversar(
    body: ConversarRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Pergunta e resposta com a base do escritório (RAG) — inclui pesquisa."""
    return await _porta("conversar", body, db, cu)


@router.post("/extrair", response_model=RespostaCapacidadeIA,
             dependencies=[Depends(rate_limit("ia-cap-extrair", 15))])
async def extrair(
    body: ExtrairRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Extração estruturada (prazos, partes, valores, cláusulas) de um texto."""
    return await _porta("extrair", body, db, cu)
