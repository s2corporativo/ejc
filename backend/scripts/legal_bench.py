"""Executa o Legal Bench determinístico sobre respostas estruturadas.

Exemplo:
    python -m scripts.legal_bench --cases app/eval/legal_bench.synthetic.jsonl \
        --answers /tmp/respostas.jsonl

O comando não chama LLM. Ele pontua artefatos já produzidos e pode ser usado para
comparar providers/modelos/pipelines de forma reproduzível.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.eval.legal_bench import load_cases, score_structured_answer, summarize


def _load_answers(path: str | Path) -> dict[str, dict]:
    answers: dict[str, dict] = {}
    with Path(path).open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"resposta JSONL inválida na linha {lineno}: {exc}") from exc
            if not isinstance(raw, dict) or not raw.get("id"):
                raise ValueError(f"resposta da linha {lineno} precisa de campo id")
            answers[str(raw["id"])] = raw
    return answers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--answers", required=True)
    parser.add_argument("--out", help="arquivo JSON opcional com scores")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    answers = _load_answers(args.answers)
    missing = [case.id for case in cases if case.id not in answers]
    if missing:
        raise SystemExit(
            "faltam respostas para casos: " + ", ".join(sorted(missing))
        )

    scores = [score_structured_answer(case, answers[case.id]) for case in cases]
    payload = {
        "summary": summarize(scores),
        "scores": [score.to_dict() for score in scores],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
