from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "ejc-adaptive-bench/1"
DIFFICULTIES = ("normal", "complexo", "fronteira", "excepcional")

WEIGHTS = {
    "facts": 10,
    "issues": 15,
    "legal_framing": 15,
    "sources": 15,
    "evidence": 10,
    "strategy": 10,
    "adverse": 10,
    "procedural": 5,
    "uncertainty": 5,
    "conclusion": 5,
}


def _s(values: Any) -> set[str]:
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(v).strip() for v in values if str(v).strip()}


def _recall(expected: set[str], actual: set[str]) -> float | None:
    if not expected:
        return None
    return round(len(expected & actual) / len(expected), 4)


@dataclass(frozen=True)
class AdaptiveCase:
    id: str
    area: str
    difficulty: str
    expected: dict[str, set[str]]
    trap_keys: set[str]
    requires_uncertainty: bool
    strict_fact_grounding: bool
    simulated_answer: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AdaptiveCase":
        case_id = str(raw.get("id") or "").strip()
        if not case_id:
            raise ValueError("caso sem id")
        difficulty = str(raw.get("difficulty") or "").strip().lower()
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"{case_id}: difficulty inválida: {difficulty!r}")
        expected_raw = raw.get("expected") or {}
        return cls(
            id=case_id,
            area=str(raw.get("area") or "nao_definida").strip().lower(),
            difficulty=difficulty,
            expected={k: _s(expected_raw.get(k)) for k in WEIGHTS if k != "uncertainty"},
            trap_keys=_s(raw.get("trap_keys")),
            requires_uncertainty=bool(raw.get("requires_uncertainty", False)),
            strict_fact_grounding=bool(raw.get("strict_fact_grounding", True)),
            simulated_answer=raw.get("simulated_answer") if isinstance(raw.get("simulated_answer"), dict) else None,
        )


def score_case(case: AdaptiveCase, answer: dict[str, Any]) -> dict[str, Any]:
    dims: dict[str, float | None] = {}
    weighted = 0.0
    denominator = 0

    mapping = {
        "facts": "fact_ids",
        "issues": "issue_keys",
        "legal_framing": "legal_framing_keys",
        "sources": "source_ids",
        "evidence": "evidence_gap_keys",
        "strategy": "strategy_keys",
        "adverse": "adverse_keys",
        "procedural": "procedural_risk_keys",
        "conclusion": "conclusion_keys",
    }

    for dim, answer_key in mapping.items():
        expected = case.expected.get(dim, set())
        value = _recall(expected, _s(answer.get(answer_key)))
        dims[dim] = value
        if value is not None:
            weighted += value * WEIGHTS[dim]
            denominator += WEIGHTS[dim]

    if case.requires_uncertainty:
        status = str(answer.get("conclusion_status") or "").strip().lower()
        value = 1.0 if status in {
            "insuficiente", "evidencia_insuficiente", "requer_saneamento",
            "sem_conclusao_segura",
        } else 0.0
        dims["uncertainty"] = value
        weighted += value * WEIGHTS["uncertainty"]
        denominator += WEIGHTS["uncertainty"]
    else:
        dims["uncertainty"] = None

    allowed_facts = case.expected.get("facts", set())
    actual_facts = _s(answer.get("fact_ids"))
    invented_facts = sorted(actual_facts - allowed_facts) if allowed_facts else []
    citation_failures = [
        str(x) for x in (answer.get("citation_failures") or []) if str(x).strip()
    ]
    forbidden_claims = [
        str(x) for x in (answer.get("forbidden_claims") or []) if str(x).strip()
    ]
    detected_traps = _s(answer.get("detected_traps"))
    missed_traps = sorted(case.trap_keys - detected_traps)

    critical_reasons: list[str] = []
    if citation_failures:
        critical_reasons.append("citação inexistente/incorreta")
    if forbidden_claims:
        critical_reasons.append("afirmação proibida")
    if case.strict_fact_grounding and invented_facts:
        critical_reasons.append("fato inventado")

    raw_score = round((weighted / denominator) * 100, 2) if denominator else 0.0
    certification_score = 0.0 if critical_reasons else raw_score

    return {
        "id": case.id,
        "area": case.area,
        "difficulty": case.difficulty,
        "raw_score": raw_score,
        "certification_score": certification_score,
        "critical_failure": bool(critical_reasons),
        "critical_reasons": critical_reasons,
        "citation_failures": citation_failures,
        "forbidden_claims": forbidden_claims,
        "invented_facts": invented_facts,
        "trap_recall": (
            round(len(case.trap_keys & detected_traps) / len(case.trap_keys), 4)
            if case.trap_keys else None
        ),
        "missed_traps": missed_traps,
        "dimensions": dims,
    }


def load_cases(path: str | Path) -> list[AdaptiveCase]:
    rows: list[AdaptiveCase] = []
    seen: set[str] = set()
    with Path(path).open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            raw = json.loads(line)
            case = AdaptiveCase.from_dict(raw)
            if case.id in seen:
                raise ValueError(f"id duplicado na linha {lineno}: {case.id}")
            seen.add(case.id)
            rows.append(case)
    return rows


def load_answers(path: str | Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            raw = json.loads(line)
            out[str(raw["id"])] = raw.get("answer") or {}
    return out


def summarize(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)

    def block(items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {"n": 0, "score": None, "critical_failures": 0, "trap_recall": None}
        trap_values = [r["trap_recall"] for r in items if r["trap_recall"] is not None]
        return {
            "n": len(items),
            "score": round(sum(r["certification_score"] for r in items) / len(items), 2),
            "raw_score": round(sum(r["raw_score"] for r in items) / len(items), 2),
            "critical_failures": sum(1 for r in items if r["critical_failure"]),
            "trap_recall": round(sum(trap_values) / len(trap_values), 4) if trap_values else None,
        }

    by_difficulty = {
        d: block([r for r in rows if r["difficulty"] == d]) for d in DIFFICULTIES
    }
    by_area = {
        area: block([r for r in rows if r["area"] == area])
        for area in sorted({r["area"] for r in rows})
    }
    return {
        "schema": SCHEMA,
        "global": block(rows),
        "by_difficulty": by_difficulty,
        "by_area": by_area,
    }


def main(argv: list[str] | None = None) -> int:
    base = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description="Benchmark jurídico adaptativo EJC")
    p.add_argument("--gold", default=str(base / "gold_set_adaptive.synthetic.jsonl"))
    p.add_argument("--answers")
    p.add_argument("--simulate", action="store_true")
    p.add_argument("--out")
    p.add_argument("--max-critical", type=int, default=None)
    p.add_argument("--min-score", type=float, default=None)
    args = p.parse_args(argv)

    cases = load_cases(args.gold)
    answers = load_answers(args.answers) if args.answers else {}
    results: list[dict[str, Any]] = []
    for case in cases:
        if args.simulate:
            answer = case.simulated_answer or {}
        else:
            if case.id not in answers:
                raise SystemExit(f"resposta ausente para {case.id}; use --answers ou --simulate")
            answer = answers[case.id]
        results.append(score_case(case, answer))

    summary = summarize(results)
    payload = {"summary": summary, "cases": results}
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.out:
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    g = summary["global"]
    failures = []
    if args.max_critical is not None and g["critical_failures"] > args.max_critical:
        failures.append(
            f"falhas críticas {g['critical_failures']} > {args.max_critical}"
        )
    if args.min_score is not None and (g["score"] or 0) < args.min_score:
        failures.append(f"score {g['score']} < {args.min_score}")
    if failures:
        for item in failures:
            print(f"FALHA: {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
