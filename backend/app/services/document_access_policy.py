"""Política de visibilidade de documentos por confidencialidade.

Acesso ao cliente/caso não implica acesso a todos os documentos daquele
contexto. O GED possui um cofre adicional: abaixo de sócio, somente documentos
``normal`` e ``interno`` são visíveis. Esta função é deliberadamente pura para
ser reutilizada por superfícies derivadas (Raio-X, Data Room, etc.) sem importar
helpers privados de routers.
"""
from __future__ import annotations

from app.core.security import ROLE_LEVEL
from app.models.document import DocConfidencialidade
from app.models.user import User

_CONFIDENCIALIDADES_EQUIPE = (
    DocConfidencialidade.normal,
    DocConfidencialidade.interno,
)
_CONFIDENCIALIDADES_SOCIO = tuple(DocConfidencialidade)


def _role_value(user: User) -> str:
    role = getattr(user, "role", "")
    return getattr(role, "value", str(role))


def confidencialidades_visiveis(user: User) -> tuple[DocConfidencialidade, ...]:
    """Retorna o conjunto fechado que pode compor consultas SQL do usuário."""
    if ROLE_LEVEL.get(_role_value(user), 0) >= ROLE_LEVEL["socio"]:
        return _CONFIDENCIALIDADES_SOCIO
    return _CONFIDENCIALIDADES_EQUIPE


def pode_acessar_confidencialidade(
    user: User,
    confidencialidade: DocConfidencialidade | str,
) -> bool:
    """Validação de objeto já carregado; mantém a mesma política da query."""
    try:
        value = (
            confidencialidade
            if isinstance(confidencialidade, DocConfidencialidade)
            else DocConfidencialidade(confidencialidade)
        )
    except (TypeError, ValueError):
        return False
    return value in confidencialidades_visiveis(user)


from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import verificar_acesso_caso
from app.models.case import Case
from app.models.document import Document

_COFRE_RESTRITO = {
    DocConfidencialidade.restrito,
    DocConfidencialidade.confidencial,
    DocConfidencialidade.segredo_justica,
}


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
