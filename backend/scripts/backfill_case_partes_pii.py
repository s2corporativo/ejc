"""Backfill do CPF/CNPJ das partes para as colunas cifradas (migration 159).

Uso (WORKDIR backend/, mesmas variáveis de ambiente do app —
PII_ENCRYPTION_KEY e PII_HASH_KEY obrigatórias):

    python scripts/backfill_case_partes_pii.py

Idempotente e best-effort: só cifra linhas com texto puro e sem cifra; não
apaga o texto puro (CONTRACT é migration futura); se o schema ainda não tem a
migration 159, sai com código 0 avisando — nunca derruba o boot do container.
Ver app/services/case_parte_pii.py.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main() -> int:
    from app.core.database import AsyncSessionLocal, engine
    from app.services.case_parte_pii import backfill_case_partes_pii

    try:
        async with AsyncSessionLocal() as db:
            resumo = await backfill_case_partes_pii(db)
    finally:
        await engine.dispose()
    if resumo.get("motivo") == "schema_sem_migration_159":
        print("[backfill_case_partes_pii] colunas cifradas ausentes (migration 159 "
              "não aplicada) — nada a fazer.")
        return 0
    print(f"[backfill_case_partes_pii] cifradas={resumo['cifradas']} "
          f"ignoradas_sem_digitos={resumo['ignoradas_sem_digitos']} lotes={resumo['lotes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
