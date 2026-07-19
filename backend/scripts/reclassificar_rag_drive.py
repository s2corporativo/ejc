#!/usr/bin/env python
"""Reclassifica documentos Google Drive já ingeridos no RAG.

Uso seguro na VPS:

    # Simular sem alterar banco
    docker compose exec backend python scripts/reclassificar_rag_drive.py --dry-run --only-changes

    # Aplicar após revisar o dry-run
    docker compose exec backend python scripts/reclassificar_rag_drive.py --apply --only-changes

A rotina não apaga documentos. Arquivos sinalizados como teste/rascunho/backup
são marcados como vigente=false quando --apply é usado, preservando histórico.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.core.database import AsyncSessionLocal, engine
from app.services.rag_drive_reclassifier import reclassificar_docs_drive


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audita/reclassifica knowledge_docs originados do Google Drive."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra alterações sugeridas sem persistir no banco.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Aplica reclassificação no banco. Use somente após revisar o dry-run.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limita quantidade de documentos lidos.")
    parser.add_argument(
        "--only-changes",
        action="store_true",
        help="Exibe apenas documentos cuja categoria/vigência mudaria.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Arquivo JSON para salvar o relatório. Ex.: /tmp/rag-drive-reclassificacao.json",
    )
    return parser


def _print_summary(payload: dict[str, Any]) -> None:
    print(json.dumps({
        "modo": payload["modo"],
        "total_docs_drive_lidos": payload["total_docs_drive_lidos"],
        "total_resultados": payload["total_resultados"],
        "total_alterariam": payload["total_alterariam"],
        "total_aplicados": payload["total_aplicados"],
        "por_categoria_final": payload["por_categoria_final"],
        "por_tipo_fonte": payload["por_tipo_fonte"],
        "por_area_juridica": payload["por_area_juridica"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


async def _run() -> int:
    args = _build_parser().parse_args()
    async with AsyncSessionLocal() as db:
        payload = await reclassificar_docs_drive(
            db,
            apply=args.apply,
            limit=args.limit,
            only_changes=args.only_changes,
        )

    _print_summary(payload)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"Relatório salvo em: {args.output}")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
