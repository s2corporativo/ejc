from __future__ import annotations

from sqlalchemy import func, or_, select

from app.core.ownership import is_gestao
from app.core.security import ROLE_LEVEL
from app.models.document import Document
from app.models.user import User


def role_value(user: User) -> str:
    """Normaliza role SQLAlchemy Enum/str sem depender de str(Enum)."""
    role = getattr(user, "role", None)
    return str(getattr(role, "value", role) or "")


from app.services.diario_oficial_scope import visible_alerts_query as visible_alerts_query


def visible_document_count_query(
    user: User,
    *,
    client_id: str,
    visible_case_ids: list[str],
):
    """Conta somente documentos que o usuário enxergaria no GED canônico.

    O perfil empresarial já foi autorizado antes desta chamada. Ainda assim,
    documentos têm cofre/ownership próprios: advogado não pode ganhar acesso a
    anexos restritos ou a casos de terceiros só porque o mesmo cliente é visível.
    """
    scope = [Document.client_id == client_id]
    if visible_case_ids:
        scope.append(Document.case_id.in_(visible_case_ids))

    query = select(func.count(Document.id)).where(
        Document.deleted_at.is_(None),
        or_(*scope),
    )

    if ROLE_LEVEL.get(role_value(user), 0) < ROLE_LEVEL["socio"]:
        query = query.where(Document.confidencialidade.in_(["normal", "interno"]))

    if is_gestao(user):
        return query

    if not visible_case_ids:
        # O endpoint canônico de documentos não libera documentos avulsos do
        # cliente a advogado sem caso visível. Fail-closed no Legal Twin também.
        return query.where(Document.id.is_(None))

    return query.where(
        or_(
            Document.case_id.in_(visible_case_ids),
            (
                Document.case_id.is_(None)
                & (Document.client_id == client_id)
            ),
        )
    )
