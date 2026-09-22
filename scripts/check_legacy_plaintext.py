#!/usr/bin/env python3
"""Audita PII plaintext legado antes do cutover destrutivo de DB-03/BE-11.

Saída JSON e códigos: 0 quando ambos os contadores são zero, 2 quando há
legado ainda presente, 3 quando não foi possível consultar o banco. O script
nunca atualiza ou remove dados.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

QUERIES = {
    "case_partes": """
        SELECT count(*)::bigint AS total
        FROM case_partes
        WHERE cpf_cnpj IS NOT NULL OR email IS NOT NULL OR telefone IS NOT NULL
    """,
    "trabalhista_cases": """
        SELECT count(*)::bigint AS total
        FROM trabalhista_cases
        WHERE cid IS NOT NULL
    """,
}


def _parse_url() -> str:
    return os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL", "")


async def audit(database_url: str) -> dict[str, Any]:
    import asyncpg

    url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(url)
    try:
        counts = {}
        for table, query in QUERIES.items():
            counts[table] = int(await conn.fetchval(query))
    finally:
        await conn.close()
    return {
        "legacy_plaintext_count": sum(counts.values()),
        "counts": counts,
        "safe_for_phase_b": all(value == 0 for value in counts.values()),
        "destructive": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=_parse_url())
    args = parser.parse_args()
    if not args.database_url:
        print(json.dumps({"error": "DATABASE_URL ausente", "destructive": False}), file=sys.stderr)
        return 3
    try:
        result = asyncio.run(audit(args.database_url))
    except Exception as exc:  # diagnóstico deve distinguir infra de dados
        print(json.dumps({"error": type(exc).__name__, "destructive": False}))
        return 3
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["safe_for_phase_b"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
