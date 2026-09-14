from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class LegalBenchCase:
    id: str
    area: str
    prompt: str
    expected_issue_keys: tuple[str, ...] = ()
    expected_source_ids: tuple[str, ...] = ()
    allowed_fact_ids: tuple[str, ...] = ()
    requires_adverse_research: bool = True
    has_missing_evidence: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LegalBenchCase":
        return cls(
            id=str(raw["id"]),
            area=str(raw.get("area") or "nao_definida"),
            prompt=str(raw["prompt"]),
            expected_issue_keys=tuple(str(v) for v in raw.get("expected_issue_keys", [])),
            expected_source_ids=tuple(str(v) for v in raw.get("expected_source_ids", [])),
            allowed_fact_ids=tuple(str(v) for v in raw.get("allowed_fact_ids", [])),
            requires_adverse_research=bool(raw.get("requires_adverse_research", True)),
            has_missing_evidence=bool(raw.get("has_missing_evidence", False)),
        )


@dataclass(frozen=True)
class LegalBenchScore:
    case_id: str
    issue_recall: float
    source_precision: float
    fact_grounding: float
    adverse_coverage: float
    uncertainty_compliance: float

    @property
    def total(self) -> float:
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
    if not expected:
        return 1.0
    return round(len(expected & actual) / len(expected), 4)


def _precision(expected: set[str], actual: set[str]) -> float:
    if not actual:
        return 1.0 if not expected else 0.0
    return round(len(expected & actual) / len(actual), 4)


def score_structured_answer(
    case: LegalBenchCase,
    answer: dict[str, Any],
) -> LegalBenchScore:
    """Pontua saída estruturada sem usar LLM-as-judge.

    Contrato esperado da resposta avaliada:
    ``issue_keys``, ``source_ids``, ``fact_ids``, ``adverse_research_done`` e
    ``conclusion_status``. Métricas semânticas/qualitativas podem ser adicionadas
    por uma camada humana ou juiz separado, mas este baseline permanece
    reproduzível e barato.
    """

    issue_keys = {str(v) for v in answer.get("issue_keys", [])}
    source_ids = {str(v) for v in answer.get("source_ids", [])}
    fact_ids = {str(v) for v in answer.get("fact_ids", [])}
    expected_issues = set(case.expected_issue_keys)
    expected_sources = set(case.expected_source_ids)
    allowed_facts = set(case.allowed_fact_ids)

    issue_recall = _ratio(expected_issues, issue_keys)
    source_precision = _precision(expected_sources, source_ids)

    if not fact_ids:
        fact_grounding = 1.0
    elif not allowed_facts:
        fact_grounding = 0.0
    else:
        fact_grounding = round(len(fact_ids & allowed_facts) / len(fact_ids), 4)

    if case.requires_adverse_research:
        adverse_coverage = 1.0 if answer.get("adverse_research_done") is True else 0.0
    else:
        adverse_coverage = 1.0

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
    cases: list[LegalBenchCase] = []
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
            cases.append(LegalBenchCase.from_dict(raw))
    return cases


def summarize(scores: Iterable[LegalBenchScore]) -> dict[str, float | int]:
    rows = list(scores)
    if not rows:
        return {"n": 0, "total": 0.0}

    def avg(field: str) -> float:
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
