"""Normalização defensiva da Sala Jurídica na fronteira ORM.

Não altera schema nem reescreve histórico. Corrige em memória dois formatos
legados que não devem escapar para a UI:

* ``area_sugerida`` só pode expor um slug canônico de ``CaseArea``;
* ``citacoes`` só pode expor uma lista de objetos, nunca as antigas chaves
  string do relatório do gate anti-alucinação.

A normalização roda tanto em atribuições novas quanto ao carregar registros
legados. ``set_committed_value`` evita marcar o objeto como dirty apenas por
termos saneado a representação de leitura.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm.attributes import set_committed_value

from app.models.case import CaseArea
from app.models.legal_chat import LegalChatMessage, LegalChatSession

_AREAS_CANONICAS = {area.value for area in CaseArea}


def normalizar_area_sugerida(value: Any) -> str | None:
    """Devolve somente slugs aceitos pelo fluxo canônico de criação de caso."""
    if isinstance(value, str) and value in _AREAS_CANONICAS:
        return value
    return None


def normalizar_citacoes(value: Any) -> list[dict[str, Any]]:
    """Remove formato legado/malformado sem inventar conteúdo jurídico."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


@event.listens_for(LegalChatSession.area_sugerida, "set", retval=True)
def _normalizar_area_ao_atribuir(_target, value, _oldvalue, _initiator):
    return normalizar_area_sugerida(value)


@event.listens_for(LegalChatSession, "load")
def _normalizar_area_ao_carregar(target: LegalChatSession, _context) -> None:
    normalizada = normalizar_area_sugerida(target.area_sugerida)
    if normalizada != target.area_sugerida:
        set_committed_value(target, "area_sugerida", normalizada)


@event.listens_for(LegalChatMessage.citacoes, "set", retval=True)
def _normalizar_citacoes_ao_atribuir(_target, value, _oldvalue, _initiator):
    return normalizar_citacoes(value)


@event.listens_for(LegalChatMessage, "load")
def _normalizar_citacoes_ao_carregar(target: LegalChatMessage, _context) -> None:
    normalizadas = normalizar_citacoes(target.citacoes)
    if normalizadas != (target.citacoes or []):
        set_committed_value(target, "citacoes", normalizadas)
