from __future__ import annotations

from dataclasses import dataclass, replace

from .contracts import EvidenceState


@dataclass(frozen=True)
class CaseAssertion:
    """Afirmação do caso com estado epistemológico e trilha de validação."""

    id: str
    text: str
    state: EvidenceState
    source_ids: tuple[str, ...] = ()
    validated_by_user_id: str | None = None
    validated_at: str | None = None

    def __post_init__(self) -> None:
        """Impede construir estado validado sem identidade e data do revisor."""

        if self.state in {
            EvidenceState.VALIDADO_ADVOGADO,
            EvidenceState.CONFIRMADO,
        } and (not self.validated_by_user_id or not self.validated_at):
            raise ValueError(
                "estado probatório validado exige revisor autenticado e data"
            )


# Transições explícitas. Inferência nunca vira CONFIRMADO diretamente; para
# adquirir valor humano ela passa por VALIDADO_ADVOGADO, com identidade e data.
_ALLOWED_TRANSITIONS: dict[EvidenceState, set[EvidenceState]] = {
    EvidenceState.ALEGADO_CLIENTE: {
        EvidenceState.CONTROVERTIDO,
        EvidenceState.VALIDADO_ADVOGADO,
        EvidenceState.DESCARTADO,
    },
    EvidenceState.ALEGADO_PARTE_CONTRARIA: {
        EvidenceState.CONTROVERTIDO,
        EvidenceState.VALIDADO_ADVOGADO,
        EvidenceState.DESCARTADO,
    },
    EvidenceState.CONTROVERTIDO: {
        EvidenceState.VALIDADO_ADVOGADO,
        EvidenceState.DESCARTADO,
    },
    EvidenceState.INFERENCIA_IA: {
        EvidenceState.VALIDADO_ADVOGADO,
        EvidenceState.DESCARTADO,
    },
    EvidenceState.CONFIRMADO: {
        EvidenceState.CONTROVERTIDO,
        EvidenceState.DESCARTADO,
    },
    EvidenceState.VALIDADO_ADVOGADO: {
        EvidenceState.CONTROVERTIDO,
        EvidenceState.CONFIRMADO,
        EvidenceState.DESCARTADO,
    },
    EvidenceState.DESCARTADO: set(),
}


def transition_assertion(
    assertion: CaseAssertion,
    target: EvidenceState,
    *,
    reviewer_user_id: str | None = None,
    reviewed_at: str | None = None,
) -> CaseAssertion:
    """Aplica transição fail-closed no estado probatório.

    Promoções humanas exigem identificador do revisor e timestamp. O serviço não
    consulta usuários nem inventa identidade; isso deve vir do contexto
    autenticado no caller.
    """

    if target == assertion.state:
        return assertion
    allowed = _ALLOWED_TRANSITIONS.get(assertion.state, set())
    if target not in allowed:
        raise ValueError(
            f"transição probatória inválida: {assertion.state.value} -> {target.value}"
        )

    if target in {EvidenceState.VALIDADO_ADVOGADO, EvidenceState.CONFIRMADO}:
        if not reviewer_user_id or not reviewed_at:
            raise ValueError("promoção probatória exige revisor autenticado e data")

    return replace(
        assertion,
        state=target,
        validated_by_user_id=reviewer_user_id
        if target in {EvidenceState.VALIDADO_ADVOGADO, EvidenceState.CONFIRMADO}
        else assertion.validated_by_user_id,
        validated_at=reviewed_at
        if target in {EvidenceState.VALIDADO_ADVOGADO, EvidenceState.CONFIRMADO}
        else assertion.validated_at,
    )
