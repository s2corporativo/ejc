"""Política de acesso a documentos reutilizável fora do router do GED.

Módulos de domínio que recebem ``document_id`` não devem importar helpers
privados de ``app.routers.documents``. Esta camada concentra os invariantes
mínimos de vínculo documento↔caso e cofre, preservando a direção
``router -> service -> model``.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import role_str, verificar_acesso_caso
from app.core.security import ROLE_LEVEL
from app.models.case import Case
from app.models.document import DocConfidencialidade, Document
from app.models.user import User

_COFRE_RESTRITO = {
    DocConfidencialidade.restrito,
    DocConfidencialidade.confidencial,
    DocConfidencialidade.segredo_justica,
}


def pode_acessar_confidencialidade(user: User, conf: DocConfidencialidade) -> bool:
    """Aplica o mesmo piso do cofre do GED sem depender da camada HTTP."""

    if conf not in _COFRE_RESTRITO:
        return True
    return ROLE_LEVEL.get(role_str(user), 0) >= ROLE_LEVEL["socio"]


async def exigir_documento_compativel_com_caso(
    db: AsyncSession,
    user: User,
    *,
    document_id: str,
    case: Case,
) -> Document:
    """Valida documento ativo, tenant e cofre contra um caso já autorizado."""

    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    if doc.case_id != case.id:
        raise HTTPException(
            status_code=400,
            detail="Documento não pertence ao caso informado",
        )

    if doc.client_id and case.client_id and doc.client_id != case.client_id:
        # Estado legado inconsistente: falhar fechado, sem tentar reparar na
        # escrita financeira e sem expor qual cliente está associado ao arquivo.
        raise HTTPException(
            status_code=409,
            detail="Documento possui vínculo de cliente incompatível com o caso",
        )

    if not pode_acessar_confidencialidade(user, doc.confidencialidade):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")

    return doc


async def exigir_documento_acessivel_no_caso(
    db: AsyncSession,
    user: User,
    *,
    document_id: str,
    case_id: str,
) -> Document:
    """Valida ownership do caso e delega os invariantes documento↔caso.

    A mensagem de vínculo inválido é deliberadamente genérica para não revelar
    a qual caso/cliente pertence um ``document_id`` obtido fora do escopo do
    usuário.
    """

    case = await verificar_acesso_caso(db, user, case_id)
    return await exigir_documento_compativel_com_caso(
        db,
        user,
        document_id=document_id,
        case=case,
    )
