from __future__ import annotations

from sqlalchemy import func, or_, select

from app.core.ownership import is_gestao
from app.core.security import ROLE_LEVEL
from app.models.case import Case
from app.models.diario_oficial import DiarioOficialAlerta
from app.models.document import Document
from app.models.user import User


def role_value(user: User) -> str:
    """Normaliza role SQLAlchemy Enum/str sem depender de str(Enum)."""
    role = getattr(user, "role", None)
    return str(getattr(role, "value", role) or "")


def visible_alerts_query(user: User):
    """Replica o contrato canônico do Diário Oficial para leituras DPT.

    Gestão vê todos os alertas. Advogado vê alertas office-wide (sem case_id) e
    alertas ligados a casos em que é responsável/auxiliar. Nenhuma rota DPT
    pode ampliar essa superfície.
    """
    query = select(DiarioOficialAlerta)
    if is_gestao(user):
        return query

    visible_cases = select(Case.id).where(
        Case.deleted_at.is_(None),
        or_(
            Case.advogado_responsavel_id == user.id,
            Case.advogado_auxiliar_id == user.id,
        ),
    )
    return query.where(
        or_(
            DiarioOficialAlerta.case_id.is_(None),
            DiarioOficialAlerta.case_id.in_(visible_cases),
        )
    )


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
