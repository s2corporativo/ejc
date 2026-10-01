from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

SCHEMA = "ejc-provider-quality/1"


def build(rows: list[dict], *, certified: bool, holdout: bool, gold_hash: str | None,
          holdout_hash: str | None) -> dict:
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(
            str(row.get("area") or "geral").lower(),
            str(row.get("task_type") or "default").lower(),
            str(row.get("provider") or "").lower(),
        )].append(row)

    areas: dict = {}
    for (area, task, provider), items in grouped.items():
        if not provider:
            continue
        scores = [float(i.get("score") or 0.0) for i in items]
        if scores and max(scores) > 1.0:
            scores = [s / 100.0 for s in scores]
        costs = [float(i.get("cost_brl") or 0.0) for i in items]
        critical = sum(1 for i in items if bool(i.get("critical_failure")))
        areas.setdefault(area, {}).setdefault(task, {"providers": {}})
        areas[area][task]["providers"][provider] = {
            "n": len(items),
            "score": round(mean(scores), 4) if scores else 0.0,
            "critical_failures": critical,
            "avg_cost_brl": round(mean(costs), 6) if costs else 0.0,
        }

    return {
        "schema": SCHEMA,
        "certified": bool(certified),
        "holdout_evaluated": bool(holdout),
        "gold_sha256": gold_hash,
        "holdout_sha256": holdout_hash,
        "areas": areas,
        "notice": (
            "certified=true deve representar curadoria humana real; este gerador "
            "não atesta casos nem confere fontes por conta própria"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gera artefato de qualidade para roteamento adaptativo")
    p.add_argument("--input", required=True, help="JSONL: area/task_type/provider/score/cost_brl/critical_failure")
    p.add_argument("--out", required=True)
    p.add_argument("--certified", action="store_true")
    p.add_argument("--holdout-evaluated", action="store_true")
    p.add_argument("--gold-sha256")
    p.add_argument("--holdout-sha256")
    args = p.parse_args(argv)

    rows = []
    with Path(args.input).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip() and not line.lstrip().startswith("#"):
                rows.append(json.loads(line))
    report = build(
        rows,
        certified=args.certified,
        holdout=args.holdout_evaluated,
        gold_hash=args.gold_sha256,
        holdout_hash=args.holdout_sha256,
    )
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
