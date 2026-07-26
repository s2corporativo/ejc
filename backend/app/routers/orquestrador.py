# ── app/routers/orquestrador.py ──────────────────────────────────────────────
# FASE 5 do Orquestrador Jurídico — LegalCaseOrchestrator (máquina de estados).
#
# GET  /cases/{case_id}/orquestrador          → estado derivado dos artefatos +
#      próximo passo + pendências bloqueantes + jornada (UI) + linha do tempo.
# POST /cases/{case_id}/orquestrador/avancar  → executa UMA transição via os
#      services já existentes. Advogado+; ownership; rate limit 10/min;
#      whitelist de ações (desconhecida = 422). Atos jurídicos (aprovações /
#      confirmação de termo) NUNCA são executados — a resposta devolve a
#      instrução do endpoint de aprovação humana próprio.
#
# Gates: verificar_acesso_caso (RBAC+ABAC) em TODOS; zero LLM aqui — a IA já
# vive dentro dos services chamados pelas ações.
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.user import User
from app.services import legal_case_orchestrator as lco

logger = logging.getLogger("ejc.orquestrador")

router = APIRouter(prefix="/cases/{case_id}/orquestrador",
                   tags=["Orquestrador Jurídico"])


def _pode_avancar(cu: User) -> bool:
    """Mesmo limiar do Motor de Peça/intake: advogado+."""
    role = getattr(cu.role, "value", cu.role)
    return ROLE_LEVEL.get(role, 0) >= ROLE_LEVEL["advogado"]


class AvancarIn(BaseModel):
    """Uma transição da máquina de estados (whitelist em lco.ACOES_VALIDAS)."""
    acao: str = Field(..., max_length=64)
    params: Optional[dict] = None


@router.get("")
async def visao(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Estado atual (derivado de artefatos reais), próximo passo recomendado,
    pendências bloqueantes, jornada resumida p/ UI e linha do tempo."""
    case = await verificar_acesso_caso(db, cu, case_id)
    return await lco.visao_orquestrador(db, case_id, case=case)


@router.post(
    "/avancar",
    dependencies=[Depends(rate_limit("orquestrador-avancar", 10))],
)
async def avancar(
    case_id: str,
    body: AvancarIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Executa UMA transição pela whitelist do orquestrador (advogado+).

    Ação desconhecida → 422. Atos jurídicos são recusados com a instrução do
    endpoint humano próprio (o orquestrador nunca aprova nada sozinho)."""
    if not _pode_avancar(cu):
        raise HTTPException(403, "Orquestrador restrito a advogados")
    case = await verificar_acesso_caso(db, cu, case_id)
    # Guarda mínima (review PR #483): caso encerrado/arquivado não executa
    # nenhuma ação — o advogado precisa reabrir/desarquivar antes (fluxo
    # próprio em /cases/{id}). Espelha o bloqueio de edição do restante do EJC.
    status_caso = getattr(case.status, "value", case.status)
    if status_caso in ("encerrado", "arquivado"):
        raise HTTPException(
            409,
            f"Caso {status_caso} — reabra o caso para executar ações "
            "do orquestrador.",
        )
    return await lco.avancar(db, case_id, cu, body.acao, body.params, case=case)
