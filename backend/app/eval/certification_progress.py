from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.eval.gold_governance import auditar_diretorio

AREAS_BASE = ("consumidor", "trabalhista", "civel", "penal", "tributario")
STAGES = (
    {"name": "baseline_15", "total": 15, "per_area": 3},
    {"name": "validacao_30", "total": 30, "per_area": 6},
    {"name": "robustez_50", "total": 50, "per_area": 10},
    {"name": "certificacao_75", "total": 75, "per_area": 15},
)


def progress(base: str | Path, areas: tuple[str, ...] = AREAS_BASE) -> dict:
    audit = auditar_diretorio(base)
    stages = []
    for stage in STAGES:
        missing = {
            area: max(0, stage["per_area"] - int(audit.por_area.get(area, 0)))
            for area in areas
        }
        ready = (
            not audit.erros
            and audit.casos_reais >= stage["total"]
            and all(v == 0 for v in missing.values())
        )
        stages.append({
            **stage,
            "ready": ready,
            "missing_total": max(0, stage["total"] - audit.casos_reais),
            "missing_by_area": missing,
        })
    current = next((s["name"] for s in reversed(stages) if s["ready"]), "sem_baseline")
    return {
        "real_cases": audit.casos_reais,
        "candidate_cases": audit.casos_candidatos,
        "errors": list(audit.erros),
        "by_area": dict(audit.por_area),
        "by_scenario": dict(audit.por_cenario),
        "current_stage": current,
        "stages": stages,
        "rule": (
            "caso candidato/sintético nunca conta; cada estágio exige curadoria "
            "humana, fonte oficial, vigência e ausência de PII"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Progresso incremental do gold set humano EJC")
    p.add_argument("--base", default=str(Path(__file__).resolve().parent))
    p.add_argument("--areas", default=",".join(AREAS_BASE))
    p.add_argument("--out")
    args = p.parse_args(argv)
    areas = tuple(a.strip() for a in args.areas.split(",") if a.strip())
    report = progress(args.base, areas)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
