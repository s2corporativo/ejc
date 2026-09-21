#!/usr/bin/env python
"""Reconcilia os agregados de desempenho de teses a partir de tese_caso_links.

Dry-run por padrão. Não altera schema e não toca dados de caso/cliente.
Executar no container backend:

    python -m scripts.reconciliar_metricas_teses
    python -m scripts.reconciliar_metricas_teses --apply

Use --apply somente após backup e revisão do dry-run.
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.tese import Tese
from app.services.tese_vinculo_service import reconciliar_metricas_tese

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.reconciliar_metricas_teses")


async def executar(*, apply: bool) -> int:
    async with AsyncSessionLocal() as db:
        teses = (
            await db.execute(
                select(Tese).where(Tese.deleted_at.is_(None)).order_by(Tese.id)
            )
        ).scalars().all()

        alteradas = 0
        for tese in teses:
            antes = (
                int(tese.vezes_usada or 0),
                int(tese.vezes_venceu or 0),
                int(tese.vezes_perdeu or 0),
                tese.taxa_sucesso,
            )
            await reconciliar_metricas_tese(db, tese.id)
            depois = (
                int(tese.vezes_usada or 0),
                int(tese.vezes_venceu or 0),
                int(tese.vezes_perdeu or 0),
                tese.taxa_sucesso,
            )
            if antes != depois:
                alteradas += 1
                logger.info(
                    "tese_id=%s divergente: usos %s→%s; vitórias %s→%s; "
                    "derrotas %s→%s; taxa %s→%s",
                    tese.id,
                    antes[0],
                    depois[0],
                    antes[1],
                    depois[1],
                    antes[2],
                    depois[2],
                    antes[3],
                    depois[3],
                )

        if apply:
            await db.commit()
            logger.info(
                "Reconciliação aplicada: %d/%d tese(s) alterada(s).",
                alteradas,
                len(teses),
            )
        else:
            await db.rollback()
            logger.info(
                "Dry-run: %d/%d tese(s) divergente(s). Nada foi gravado.",
                alteradas,
                len(teses),
            )
        return alteradas


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava a reconciliação. Sem esta flag, executa somente dry-run.",
    )
    args = parser.parse_args()
    asyncio.run(executar(apply=args.apply))
