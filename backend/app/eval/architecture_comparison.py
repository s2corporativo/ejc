from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from statistics import mean


def _load(path: str) -> dict[str, float]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("cases") or raw.get("por_caso") or []
    out: dict[str, float] = {}
    for row in rows:
        case_id = str(row.get("id") or row.get("case_id") or "")
        score = row.get("certification_score")
        if score is None:
            score = row.get("score")
        if case_id and score is not None:
            val = float(score)
            if val <= 1.0:
                val *= 100.0
            out[case_id] = val
    return out


def _bootstrap_ci(deltas: list[float], *, rounds: int = 5000) -> tuple[float, float]:
    if not deltas:
        return (0.0, 0.0)
    rnd = random.Random(20261001)
    vals = []
    for _ in range(rounds):
        sample = [rnd.choice(deltas) for _ in deltas]
        vals.append(mean(sample))
    vals.sort()
    lo = vals[int(0.025 * (len(vals) - 1))]
    hi = vals[int(0.975 * (len(vals) - 1))]
    return round(lo, 2), round(hi, 2)


def compare(ejc: dict[str, float], raw: dict[str, float]) -> dict:
    common = sorted(set(ejc) & set(raw))
    if not common:
        raise ValueError("nenhum caso comum entre EJC e modelo isolado")
    rows = [
        {"id": i, "ejc": ejc[i], "raw": raw[i], "delta": round(ejc[i] - raw[i], 2)}
        for i in common
    ]
    deltas = [r["delta"] for r in rows]
    ci = _bootstrap_ci(deltas)
    return {
        "schema": "ejc-architecture-uplift/1",
        "n": len(rows),
        "ejc_mean": round(mean(r["ejc"] for r in rows), 2),
        "raw_mean": round(mean(r["raw"] for r in rows), 2),
        "delta_mean": round(mean(deltas), 2),
        "delta_ci95_bootstrap": list(ci),
        "ejc_wins": sum(1 for d in deltas if d > 0),
        "ties": sum(1 for d in deltas if d == 0),
        "raw_wins": sum(1 for d in deltas if d < 0),
        "cases": rows,
    }


def simulated() -> dict:
    # Apenas teste do MÉTODO estatístico. Números não representam desempenho real.
    raw = {f"sim-{i:02d}": s for i, s in enumerate(
        [72, 76, 68, 81, 74, 70, 79, 65, 77, 73, 69, 80], 1
    )}
    ejc = {k: min(100.0, v + d) for (k, v), d in zip(
        raw.items(), [9, 7, 13, 5, 8, 12, 6, 15, 7, 9, 11, 4]
    )}
    out = compare(ejc, raw)
    out["simulated"] = True
    out["warning"] = "SIMULAÇÃO: não mede a qualidade jurídica do EJC."
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Compara o mesmo modelo isolado versus dentro da arquitetura EJC"
    )
    p.add_argument("--ejc-report")
    p.add_argument("--raw-report")
    p.add_argument("--simulate", action="store_true")
    p.add_argument("--out")
    args = p.parse_args(argv)

    if args.simulate:
        report = simulated()
    else:
        if not args.ejc_report or not args.raw_report:
            raise SystemExit("informe --ejc-report e --raw-report, ou use --simulate")
        report = compare(_load(args.ejc_report), _load(args.raw_report))
        report["simulated"] = False

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
