from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.services.legal_brain.research_loop import evaluate_research_coverage


def _bool_field(raw: dict[str, Any], key: str, default: bool) -> bool:
    """Aceita somente booleano nativo em contratos de benchmark."""

    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"campo {key} precisa ser booleano")
    return value


@dataclass(frozen=True)
class LegalBenchCase:
    """Caso curado ou sintético usado pelo benchmark determinístico."""

    id: str
    area: str
    prompt: str
    expected_issue_keys: tuple[str, ...] = ()
    expected_source_ids: tuple[str, ...] = ()
    allowed_fact_ids: tuple[str, ...] = ()
    requires_adverse_research: bool = True
    has_missing_evidence: bool = False
    source_scoring_enabled: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LegalBenchCase":
        """Valida os campos mínimos antes de construir um caso de benchmark."""

        case_id = str(raw.get("id") or "").strip()
        prompt = str(raw.get("prompt") or "").strip()
        if not case_id:
            raise ValueError("caso de benchmark precisa de id")
        if not prompt:
            raise ValueError(f"caso {case_id} precisa de prompt")
        return cls(
            id=case_id,
            area=str(raw.get("area") or "nao_definida"),
            prompt=prompt,
            expected_issue_keys=tuple(str(v) for v in raw.get("expected_issue_keys", [])),
            expected_source_ids=tuple(str(v) for v in raw.get("expected_source_ids", [])),
            allowed_fact_ids=tuple(str(v) for v in raw.get("allowed_fact_ids", [])),
            requires_adverse_research=_bool_field(raw, "requires_adverse_research", True),
            has_missing_evidence=_bool_field(raw, "has_missing_evidence", False),
            source_scoring_enabled=_bool_field(raw, "source_scoring_enabled", True),
        )


@dataclass(frozen=True)
class LegalBenchScore:
    """Métricas determinísticas de um único caso avaliado."""

    case_id: str
    issue_recall: float
    source_precision: float
    fact_grounding: float
    adverse_coverage: float
    uncertainty_compliance: float

    @property
    def total(self) -> float:
        """Retorna média simples das cinco dimensões explícitas."""

        return round(
            (
                self.issue_recall
                + self.source_precision
                + self.fact_grounding
                + self.adverse_coverage
                + self.uncertainty_compliance
            )
            / 5,
            4,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializa o score para relatório/JSONL de comparação."""

        return {
            "case_id": self.case_id,
            "issue_recall": self.issue_recall,
            "source_precision": self.source_precision,
            "fact_grounding": self.fact_grounding,
            "adverse_coverage": self.adverse_coverage,
            "uncertainty_compliance": self.uncertainty_compliance,
            "total": self.total,
        }


def _ratio(expected: set[str], actual: set[str]) -> float:
    """Calcula recall determinístico de um conjunto esperado."""

    if not expected:
        return 1.0
    return round(len(expected & actual) / len(expected), 4)


def _precision(expected: set[str], actual: set[str]) -> float:
    """Calcula precisão determinística, incluindo o caso vazio."""

    if not actual:
        return 1.0 if not expected else 0.0
    return round(len(expected & actual) / len(actual), 4)


def score_structured_answer(
    case: LegalBenchCase,
    answer: dict[str, Any],
) -> LegalBenchScore:
    """Pontua saída estruturada sem LLM-as-judge nem autodeclaração de pesquisa.

    ``adverse_coverage`` é derivado de ``research_records`` rastreáveis pelo
    mesmo avaliador de cobertura do Legal Brain. Um booleano declarado pela
    resposta não produz pontuação. Casos estruturais podem desabilitar apenas o
    score de fontes; grounding, incerteza e contraditório continuam medidos.
    """

    issue_keys = {str(v) for v in answer.get("issue_keys", []) if str(v).strip()}
    source_ids = {str(v) for v in answer.get("source_ids", []) if str(v).strip()}
    fact_ids = {str(v) for v in answer.get("fact_ids", []) if str(v).strip()}
    expected_issues = set(case.expected_issue_keys)
    expected_sources = set(case.expected_source_ids)
    allowed_facts = set(case.allowed_fact_ids)

    issue_recall = _ratio(expected_issues, issue_keys)
    source_precision = (
        _precision(expected_sources, source_ids)
        if case.source_scoring_enabled
        else 1.0
    )

    if not fact_ids:
        fact_grounding = 1.0
    elif not allowed_facts:
        fact_grounding = 0.0
    else:
        fact_grounding = round(len(fact_ids & allowed_facts) / len(fact_ids), 4)

    research_records = answer.get("research_records") or []
    if not isinstance(research_records, list):
        research_records = []
    coverage = evaluate_research_coverage(research_records)
    adverse_coverage = (
        1.0 if (not case.requires_adverse_research or coverage.adverse_precedent) else 0.0
    )

    conclusion_status = str(answer.get("conclusion_status") or "").strip().lower()
    if case.has_missing_evidence:
        uncertainty_compliance = 1.0 if conclusion_status in {
            "insuficiente",
            "evidencia_insuficiente",
            "requer_saneamento",
            "sem_conclusao_segura",
        } else 0.0
    else:
        uncertainty_compliance = 1.0

    return LegalBenchScore(
        case_id=case.id,
        issue_recall=issue_recall,
        source_precision=source_precision,
        fact_grounding=fact_grounding,
        adverse_coverage=adverse_coverage,
        uncertainty_compliance=uncertainty_compliance,
    )


def load_cases(path: str | Path) -> list[LegalBenchCase]:
    """Carrega JSONL e rejeita IDs duplicados ou registros inválidos."""

    cases: list[LegalBenchCase] = []
    seen_ids: set[str] = set()
    with Path(path).open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL inválido na linha {lineno}: {exc}") from exc
            if not isinstance(raw, dict):
                raise ValueError(f"Caso da linha {lineno} precisa ser objeto JSON")
            case = LegalBenchCase.from_dict(raw)
            if case.id in seen_ids:
                raise ValueError(f"id de caso duplicado: {case.id}")
            seen_ids.add(case.id)
            cases.append(case)
    return cases


def summarize(scores: Iterable[LegalBenchScore]) -> dict[str, float | int]:
    """Agrega scores individuais sem ponderação oculta."""

    rows = list(scores)
    if not rows:
        return {"n": 0, "total": 0.0}

    def avg(field: str) -> float:
        """Calcula média de um campo numérico do score."""

        return round(sum(float(getattr(row, field)) for row in rows) / len(rows), 4)

    return {
        "n": len(rows),
        "issue_recall": avg("issue_recall"),
        "source_precision": avg("source_precision"),
        "fact_grounding": avg("fact_grounding"),
        "adverse_coverage": avg("adverse_coverage"),
        "uncertainty_compliance": avg("uncertainty_compliance"),
        "total": round(sum(row.total for row in rows) / len(rows), 4),
    }
