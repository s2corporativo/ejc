"""Estados e transições canônicas do Financeiro."""
from __future__ import annotations

from collections.abc import Mapping
from fastapi import HTTPException

WITHDRAWAL_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "pendente": frozenset({"aprovado", "rejeitado", "cancelado"}),
    "aprovado": frozenset({"pago", "cancelado"}),
    "rejeitado": frozenset(),
    "pago": frozenset(),
    "cancelado": frozenset(),
}

APPROVAL_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "pendente": frozenset({"aprovado", "rejeitado"}),
    "aprovado": frozenset({"consumido"}),
    "rejeitado": frozenset(),
    "consumido": frozenset(),
}

EXPENSE_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "pendente": frozenset({"pago", "cancelado"}),
    # Reabertura de baixa continua permitida como correção auditável, desde que
    # a competência esteja aberta; o router registra a alteração em audit_log.
    "pago": frozenset({"pendente", "cancelado"}),
    "cancelado": frozenset({"pendente"}),
}


def exigir_transicao(
    atual: str,
    destino: str,
    transicoes: Mapping[str, frozenset[str]],
    *,
    entidade: str,
) -> None:
    if atual == destino:
        return
    permitidos = transicoes.get(atual, frozenset())
    if destino not in permitidos:
        raise HTTPException(
            409,
            f"Transição inválida de {entidade}: {atual} → {destino}.",
        )
