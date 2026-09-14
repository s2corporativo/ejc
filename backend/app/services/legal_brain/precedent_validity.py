from __future__ import annotations

from collections.abc import Iterable

from .contracts import PrecedentPropositionStatus, PrecedentValidityResult


_RELATION_STATUS: dict[str, PrecedentPropositionStatus] = {
    "confirmed_by": PrecedentPropositionStatus.CONFIRMADA,
    "distinguished_by": PrecedentPropositionStatus.DISTINGUIDA,
    "limited_by": PrecedentPropositionStatus.LIMITADA,
    "overruled_by": PrecedentPropositionStatus.SUPERADA,
    "affected_by_theme": PrecedentPropositionStatus.AFETADA_POR_TEMA,
    "affected_by_summary": PrecedentPropositionStatus.AFETADA_POR_SUMULA,
    "affected_by_legislation": PrecedentPropositionStatus.AFETADA_POR_ALTERACAO_LEGISLATIVA,
}

# Prevalência conservadora: superação > alteração legislativa > limitação >
# distinção > tema/súmula > confirmação. Não é juízo de mérito; apenas decide
# qual relação explícita deve aparecer como alerta principal.
_PRIORITY: dict[PrecedentPropositionStatus, int] = {
    PrecedentPropositionStatus.SUPERADA: 100,
    PrecedentPropositionStatus.AFETADA_POR_ALTERACAO_LEGISLATIVA: 90,
    PrecedentPropositionStatus.LIMITADA: 80,
    PrecedentPropositionStatus.DISTINGUIDA: 70,
    PrecedentPropositionStatus.AFETADA_POR_TEMA: 60,
    PrecedentPropositionStatus.AFETADA_POR_SUMULA: 60,
    PrecedentPropositionStatus.CONFIRMADA: 40,
    PrecedentPropositionStatus.NAO_VERIFICADA: 0,
}


def evaluate_proposition_validity(
    proposition_id: str,
    relations: Iterable[dict],
) -> PrecedentValidityResult:
    """Avalia status usando somente relações explicitamente registradas.

    A ausência de relações não significa validade: retorna ``nao_verificada``.
    Relações sem ``source_id`` podem sinalizar hipótese interna, mas não promovem
    estado jurídico porque não possuem proveniência rastreável.
    """

    candidates: list[tuple[int, PrecedentPropositionStatus, str, str]] = []
    ignored: list[str] = []

    for raw in relations:
        if not isinstance(raw, dict):
            continue
        relation = str(raw.get("relation") or raw.get("type") or "").strip().lower()
        source_id = str(raw.get("source_id") or "").strip()
        status = _RELATION_STATUS.get(relation)
        if status is None:
            continue
        if not source_id:
            ignored.append(relation)
            continue
        candidates.append((_PRIORITY[status], status, relation, source_id))

    if not candidates:
        notes = ()
        if ignored:
            notes = ("relações sem proveniência foram ignoradas",)
        return PrecedentValidityResult(
            proposition_id=proposition_id,
            status=PrecedentPropositionStatus.NAO_VERIFICADA,
            notes=notes,
        )

    candidates.sort(key=lambda item: (-item[0], item[2], item[3]))
    _, status, decisive_relation, _ = candidates[0]
    related_ids = tuple(sorted({item[3] for item in candidates}))
    notes: tuple[str, ...] = ()
    if ignored:
        notes = ("relações sem proveniência foram ignoradas",)

    return PrecedentValidityResult(
        proposition_id=proposition_id,
        status=status,
        decisive_relation=decisive_relation,
        related_source_ids=related_ids,
        notes=notes,
    )
