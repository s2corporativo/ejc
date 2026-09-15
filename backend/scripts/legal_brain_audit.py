"""Auditoria somente leitura da fundação do EJC Legal Brain.

Uso no container backend:
    python -m scripts.legal_brain_audit
    python -m scripts.legal_brain_audit --json

Não executa ingestão, curadoria, reindexação, deduplicação, backfill ou chamada de
LLM. Reutiliza exclusivamente métricas canônicas existentes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.ai.core.ejc_skill_catalog import native_skill_coverage
from app.services.knowledge_governance import health_snapshot
from app.services.legal_brain.skill_contracts import native_legal_skill_contracts


async def collect() -> dict[str, Any]:
    """Coleta health canônico e cobertura de skills sem alterar estado."""

    async with AsyncSessionLocal() as db:
        health = await health_snapshot(db)
    coverage = native_skill_coverage()
    contracts = native_legal_skill_contracts()
    return {
        "read_only": True,
        "knowledge_health": health,
        "native_skill_coverage": coverage,
        "legal_skill_contracts": {
            "total": len(contracts),
            "versions": sorted({item.version for item in contracts}),
            "statuses": sorted({item.status.value for item in contracts}),
        },
    }


def _print_human(report: dict[str, Any]) -> None:
    """Imprime apenas indicadores agregados, sem conteúdo jurídico ou PII."""

    skill = report["native_skill_coverage"]
    contracts = report["legal_skill_contracts"]
    print("EJC LEGAL BRAIN — AUDITORIA SOMENTE LEITURA")
    print(f"skills nativas: {skill.get('total_native_skills', 0)}")
    print(f"contratos versionados: {contracts['total']}")
    print(f"estrutura de skills: {'OK' if skill.get('estrutura_ok') else 'REVISAR'}")
    missing = ((skill.get("legal_areas") or {}).get("missing") or [])
    print(f"áreas canônicas sem método curado: {len(missing)}")
    print("saúde do corpus: coletada pela fonte canônica knowledge_governance.health_snapshot")


async def _main() -> None:
    """Resolve argumentos e entrega relatório humano ou JSON."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="imprime JSON completo")
    args = parser.parse_args()
    report = await collect()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(report)


if __name__ == "__main__":
    asyncio.run(_main())
