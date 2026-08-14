# ── app/core/publicacao_externa.py ───────────────────────────────────────────
# Política única de "piso de papel" para publicação externa de documentos —
# fonte única compartilhada pelo Data Room (link público, Issue #547) e pelo
# Portal do Cliente (publicação explícita, Issue #698).
#
# Extraído de app/routers/data_room.py (`_pode_publicar_externamente`,
# `_confidencialidade`) para não duplicar a regra: o Portal precisava do
# MESMO piso — normal exige advogado+, restrito/confidencial exige sócio+,
# interno/segredo de justiça nunca são publicados por nenhum perfil — e
# duplicar a função teria feito as duas políticas divergirem com o tempo.
from __future__ import annotations

from app.core.security import ROLE_LEVEL
from app.models.document import DocConfidencialidade, Document
from app.models.user import User


def confidencialidade_str(doc: Document) -> str:
    """Normaliza `Document.confidencialidade` (enum ou string) para string."""
    return str(
        getattr(doc.confidencialidade, "value", doc.confidencialidade) or ""
    ).lower()


def pode_publicar_externamente(u: User, doc: Document) -> bool:
    """Política explícita de publicação, separada do acesso interno ao cofre.

    Documento `interno` e `segredo_justica` NUNCA são publicados externamente,
    por nenhum perfil — nem sócio, nem superadmin. É piso de papel, não
    hierarquia: a decisão de publicar existe além do "quem pode ver".
    """
    conf = confidencialidade_str(doc)
    nivel = ROLE_LEVEL.get(u.role.value, 0)
    if conf == DocConfidencialidade.normal.value:
        return nivel >= ROLE_LEVEL["advogado"]
    if conf in {
        DocConfidencialidade.restrito.value,
        DocConfidencialidade.confidencial.value,
    }:
        return nivel >= ROLE_LEVEL["socio"]
    return False
