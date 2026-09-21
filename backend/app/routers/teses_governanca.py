"""Router — governança de Teses (pinned, fluxo de aprovação, fork, versões).

Estende o router ``/teses`` existente sem modificá-lo. Endpoints novos:

    PATCH  /teses/{id}/governanca       — atualiza pinned/experiencia/conteudo
    POST   /teses/{id}/submit           — envia para revisão do sócio
    POST   /teses/{id}/approve          — sócio carimba (RBAC: role sócio+)
    POST   /teses/{id}/fork             — cria/upsert fork pessoal do advogado
    GET    /teses/{id}/fork             — recupera fork do usuário
    GET    /teses/{id}/versions         — histórico auditável de edições

Acesso: equipe jurídica autenticada (advogado+). Aprovação restrita a sócio.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.tese_governanca import (
    TeseApprove,
    TeseForkIn,
    TeseForkOut,
    TeseGovernancaOut,
    TeseGovernancaUpdate,
    TeseSubmitReview,
    TeseVersionOut,
)
from app.services import tese_governanca_service as svc

logger = logging.getLogger("ejc.routers.teses_governanca")
router = APIRouter(prefix="/teses", tags=["Banco de Teses — Governança"])


@router.patch("/{tese_id}/governanca", response_model=TeseGovernancaOut)
async def atualizar_governanca(
    tese_id: str,
    body: TeseGovernancaUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Atualiza pinned, experiencia_minima ou conteudo_estruturado.
    Editar conteudo_estruturado de tese aprovada reverte para rascunho."""
    from app.models.tese import Tese
    tese = await db.get(Tese, tese_id)
    if tese is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tese não encontrada.")

    if body.pinned is not None:
        tese.pinned = body.pinned
    if body.experiencia_minima is not None:
        tese.experiencia_minima = body.experiencia_minima
    if body.conteudo_estruturado is not None:
        await svc.editar_conteudo_estruturado(db, tese_id, body.conteudo_estruturado, cu)
        tese = await db.get(Tese, tese_id)

    await db.commit()
    await db.refresh(tese)
    return TeseGovernancaOut.model_validate(tese)


@router.post("/{tese_id}/submit", response_model=TeseGovernancaOut)
async def enviar_para_revisao(
    tese_id: str,
    body: TeseSubmitReview,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Advogado envia tese para revisão do sócio."""
    try:
        tese = await svc.enviar_para_revisao(db, tese_id, cu, body.note)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return TeseGovernancaOut.model_validate(tese)


@router.post("/{tese_id}/approve", response_model=TeseGovernancaOut)
async def aprovar_tese(
    tese_id: str,
    body: TeseApprove,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Sócio responsável carimba a tese — status=ativa + revisor_id + revisao_em."""
    try:
        tese = await svc.aprovar_tese(db, tese_id, cu, body.note)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return TeseGovernancaOut.model_validate(tese)


@router.post("/{tese_id}/fork", response_model=TeseForkOut)
async def criar_fork(
    tese_id: str,
    body: TeseForkIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Cria/upsert fork pessoal do advogado. Edita sem mexer no original."""
    try:
        fork = await svc.upsert_fork(db, tese_id, cu, body.conteudo, body.note)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return TeseForkOut.model_validate(fork)


@router.get("/{tese_id}/fork", response_model=Optional[TeseForkOut])
async def obter_fork(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Recupera o fork pessoal do usuário, se existir."""
    fork = await svc.get_fork(db, tese_id, cu.id)
    return TeseForkOut.model_validate(fork) if fork else None


@router.get("/{tese_id}/versions", response_model=list[TeseVersionOut])
async def listar_versoes(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Histórico auditável de edições de conteudo_estruturado."""
    return [TeseVersionOut.model_validate(v) for v in await svc.listar_versoes(db, tese_id)]
