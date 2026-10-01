from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.ai_learning import AILearningEvent, AILearningEventType


async def export(path: str, *, limit: int = 0) -> dict:
    async with AsyncSessionLocal() as db:
        q = (
            select(AILearningEvent)
            .where(
                AILearningEvent.approved.is_(True),
                AILearningEvent.benchmark_eligible.is_(True),
                AILearningEvent.event_type == AILearningEventType.correction,
            )
            .order_by(AILearningEvent.approved_at.asc(), AILearningEvent.id.asc())
        )
        if limit > 0:
            q = q.limit(limit)
        rows = (await db.execute(q)).scalars().all()

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for row in rows:
            payload = {
                "id": row.id,
                "area": row.area,
                "difficulty": row.difficulty,
                "error_type": row.error_type,
                "input": row.original_text or "",
                "ideal_output": row.corrected_text or "",
                "correction_reason": row.reason or "",
                "source_refs": row.source_refs or [],
                "provenance": {
                    "human_approved": True,
                    "independent_review": bool(
                        (row.metadata_json or {}).get("independent_review")
                    ),
                    "approved_at": (
                        row.approved_at.isoformat() if row.approved_at else None
                    ),
                },
            }
            # Cinto adicional: benchmark_eligible deve implicar revisão
            # independente. Se dado legado violar isso, não exporta.
            if not payload["provenance"]["independent_review"]:
                continue
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return {
        "path": str(out),
        "eligible_rows": len(rows),
        "exported_rows": sum(
            1 for row in rows
            if bool((row.metadata_json or {}).get("independent_review"))
        ),
        "notice": (
            "Dataset preparado para avaliação/curadoria futura. Este comando "
            "NÃO executa fine-tuning e NÃO promove modelo automaticamente."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Exporta somente correções humanas independentes para dataset supervisionado"
    )
    p.add_argument("--out", required=True)
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args(argv)
    report = asyncio.run(export(args.out, limit=args.limit))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
