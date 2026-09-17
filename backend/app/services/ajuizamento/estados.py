# ── app/services/ajuizamento/estados.py ──────────────────────────────────────
# Máquina de estados do ajuizamento. Toda transição é validada aqui e gravada
# em `judicial_filing_transicoes` (uma linha por transição, com ator e motivo).
# REVISÃO HUMANA é obrigatória: só READY_FOR_REVIEW → APPROVED, e apenas por
# ação explícita de advogado (orquestrador.aprovar exige a confirmação literal).
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.models.ajuizamento import EstadoAjuizamento as E, JudicialFilingTransicao


class TransicaoInvalida(ValueError):
    """Transição não permitida pela máquina de estados."""


TRANSICOES: dict[E, frozenset[E]] = {
    E.DRAFT: frozenset({E.PREPARING, E.CANCELLED}),
    E.PREPARING: frozenset({E.VALIDATING, E.DRAFT, E.CANCELLED}),
    E.VALIDATING: frozenset({E.INVALID, E.READY_FOR_REVIEW, E.REQUIRES_AUTHORIZATION, E.CANCELLED}),
    E.INVALID: frozenset({E.DRAFT, E.PREPARING, E.CANCELLED}),
    E.READY_FOR_REVIEW: frozenset({E.APPROVED, E.DRAFT, E.INVALID, E.CANCELLED}),
    E.APPROVED: frozenset({E.SIGNING, E.READY_TO_SUBMIT, E.DRAFT, E.CANCELLED}),
    E.SIGNING: frozenset({E.READY_TO_SUBMIT, E.APPROVED, E.FAILED, E.CANCELLED}),
    E.READY_TO_SUBMIT: frozenset({E.SUBMITTING, E.DRAFT, E.CANCELLED}),
    E.SUBMITTING: frozenset({E.SUBMITTED, E.CONFIRMED, E.FAILED, E.REQUIRES_AUTHORIZATION}),
    E.SUBMITTED: frozenset({E.CONFIRMED, E.SYNCING, E.FAILED}),
    E.CONFIRMED: frozenset({E.SYNCING}),
    E.SYNCING: frozenset({E.CONFIRMED, E.FAILED}),
    E.FAILED: frozenset({E.READY_TO_SUBMIT, E.DRAFT, E.SUBMITTED, E.CONFIRMED, E.CANCELLED}),
    E.REQUIRES_AUTHORIZATION: frozenset({E.READY_TO_SUBMIT, E.DRAFT, E.CONFIRMED, E.CANCELLED}),
    E.CANCELLED: frozenset(),
}

ESTADOS_EDITAVEIS = frozenset({E.DRAFT, E.INVALID, E.READY_FOR_REVIEW, E.REQUIRES_AUTHORIZATION, E.FAILED})
ESTADOS_TERMINAIS = frozenset({E.CANCELLED})
ESTADOS_PROTOCOLADOS = frozenset({E.SUBMITTED, E.CONFIRMED, E.SYNCING})


def pode_transicionar(de: E | str, para: E | str) -> bool:
    de_e, para_e = E(de), E(para)
    return para_e in TRANSICOES.get(de_e, frozenset())


def transicionar(
    filing: Any, para: E | str, *, ator_id: str | None, motivo: str | None = None,
    db: Any | None = None,
) -> JudicialFilingTransicao:
    """Aplica a transição no filing e devolve a linha de histórico. Quando `db`
    é informado, a linha é adicionada à sessão (commit do chamador)."""
    de = E(filing.estado) if filing.estado else None
    para_e = E(para)
    if de is not None and not pode_transicionar(de, para_e):
        raise TransicaoInvalida(f"Transição {de.value} → {para_e.value} não permitida")
    filing.estado = para_e.value
    linha = JudicialFilingTransicao(
        id=str(uuid4()), filing_id=filing.id,
        de_estado=de.value if de else None, para_estado=para_e.value,
        ator_id=ator_id, motivo=(motivo or "")[:2000] or None,
        created_at=datetime.now(timezone.utc),
    )
    if db is not None:
        db.add(linha)
    return linha
