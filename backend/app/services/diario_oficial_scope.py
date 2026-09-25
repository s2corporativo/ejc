"""Escopo compartilhado de visibilidade para alertas do Diário Oficial.

A regra pertence ao EJC Core (ownership de informação jurídica), não ao DPT360.
Extraída sem mudança de comportamento na refatoração #1843.
"""
from __future__ import annotations

from sqlalchemy import or_, select

from app.core.ownership import is_gestao
from app.models.case import Case
from app.models.diario_oficial import DiarioOficialAlerta
from app.models.user import User


def visible_alerts_query(user: User):
    """Retorna somente alertas visíveis ao usuário pelo ownership canônico.

    Gestão vê todos os alertas. Demais perfis internos autorizados veem alertas
    office-wide (sem case_id) e alertas ligados a casos em que atuam como
    responsável ou auxiliar.
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
