"""Aplicação transversal da política de confidencialidade na timeline do caso.

O serviço canônico de timeline continua responsável por normalizar os eventos.
Este adaptador apenas decora a sessão SQLAlchemy para acrescentar o predicado de
confidencialidade antes de ``ORDER BY``/``LIMIT`` em toda consulta que envolva a
tabela ``documents``. Assim, documentos do cofre não chegam a ser carregados nem
interferem na paginação para perfis abaixo de sócio.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_LEVEL
from app.models.document import DocConfidencialidade, Document
from app.models.user import User
from app.services import case_timeline_service

_RESTRICTED_LEVELS = (
    DocConfidencialidade.restrito,
    DocConfidencialidade.confidencial,
    DocConfidencialidade.segredo_justica,
)


def _role_value(user: User) -> str:
    role = getattr(user, "role", "")
    return str(getattr(role, "value", role) or "")


def _requires_document_filter(user: User) -> bool:
    return ROLE_LEVEL.get(_role_value(user), 0) < ROLE_LEVEL["socio"]


def _targets_documents(statement: Any) -> bool:
    """Identifica SELECTs cuja cláusula FROM contém a tabela canônica de GED."""
    get_final_froms = getattr(statement, "get_final_froms", None)
    if not callable(get_final_froms):
        return False
    try:
        return any(
            getattr(from_clause, "name", None) == Document.__tablename__
            for from_clause in get_final_froms()
        )
    except Exception:
        # Fail closed quanto à mutação: uma instrução desconhecida segue intacta;
        # somente SELECTs reconhecidos da tabela documents são decorados.
        return False


def _apply_document_visibility(statement: Any) -> Any:
    if not _targets_documents(statement):
        return statement
    where = getattr(statement, "where", None)
    if not callable(where):
        return statement
    return statement.where(Document.confidencialidade.notin_(_RESTRICTED_LEVELS))


class _DocumentVisibilitySession:
    """Proxy mínimo da AsyncSession que injeta o filtro no SQL antes da execução."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def execute(self, statement: Any, *args: Any, **kwargs: Any):
        return await self._db.execute(
            _apply_document_visibility(statement), *args, **kwargs
        )

    async def scalar(self, statement: Any, *args: Any, **kwargs: Any):
        return await self._db.scalar(
            _apply_document_visibility(statement), *args, **kwargs
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._db, name)


def _session_for_user(db: AsyncSession, user: User) -> AsyncSession | Any:
    if not _requires_document_filter(user):
        return db
    return _DocumentVisibilitySession(db)


async def timeline(
    db: AsyncSession,
    user: User,
    case_id: str,
    *,
    page: int,
    per_page: int,
    source_limit: int,
) -> dict[str, Any]:
    return await case_timeline_service.timeline(
        _session_for_user(db, user),
        case_id,
        page=page,
        per_page=per_page,
        source_limit=source_limit,
    )


async def operational_health(
    db: AsyncSession,
    user: User,
    case_id: str,
    *,
    stale_days: int,
) -> dict[str, Any]:
    return await case_timeline_service.operational_health(
        _session_for_user(db, user),
        case_id,
        stale_days=stale_days,
    )
