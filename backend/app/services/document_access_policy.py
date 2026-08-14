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
