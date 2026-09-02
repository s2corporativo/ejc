"""Serialização e guarda de mutações vinculadas ao ciclo de vida do caso.

O fechamento inteligente precisa garantir que uma mutação fatal (especialmente
prazo) não entre entre o diagnóstico e o commit do encerramento. O advisory lock
é transacional e usa uma chave estável por caso; não exige migration e é liberado
automaticamente em commit/rollback.

Este módulo não substitui RBAC/ownership. ``verificar_caso_editavel`` combina o
lock com o gate canônico de ownership apenas para rotas que já dependem dele.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import verificar_acesso_caso
from app.models.case import Case, CaseStatus
from app.models.user import User


async def serializar_mutacao_caso(db: AsyncSession, case_id: str) -> None:
    """Serializa fechamento e mutações críticas do mesmo caso na transação."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:chave))"),
        {"chave": f"case-mutation:{case_id}"},
    )


def garantir_caso_editavel(caso: Case) -> Case:
    """Recusa mutação jurídica em caso terminal; leitura continua permitida."""
    status = caso.status.value if hasattr(caso.status, "value") else str(caso.status)
    if status in (CaseStatus.encerrado.value, CaseStatus.arquivado.value):
        raise HTTPException(
            status_code=409,
            detail=(
                "Caso encerrado/arquivado não aceita esta alteração. "
                "Reabra ou desarquive o caso antes de continuar."
            ),
        )
    return caso


async def verificar_caso_editavel(
    db: AsyncSession,
    cu: User,
    case_id: str,
) -> Case:
    """Ownership + lock transacional + estado não terminal, nesta ordem lógica."""
    await serializar_mutacao_caso(db, case_id)
    caso = await verificar_acesso_caso(db, cu, case_id)
    return garantir_caso_editavel(caso)
