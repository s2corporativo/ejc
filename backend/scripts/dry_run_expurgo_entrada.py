#!/usr/bin/env python
# ── scripts/dry_run_expurgo_entrada.py ───────────────────────────────────────
# Dry-run manual do expurgo LGPD de rascunhos abandonados da Entrada Única
# (Issue #647 / achado B6 da auditoria do PR #640) — sem esperar o cron
# (services/scheduler.py::job_expurgo_entrada_unica, 03h50, gated por
# ENTRADA_EXPURGO_ENABLED) e sem endpoint HTTP novo: operação gated por
# acesso ao servidor, não por RBAC de app.
#
# Só CONTA — nunca apaga nada (services/entrada_expurgo_service.py sempre
# roda com dry_run=True aqui). Para o modo real, ligue ENTRADA_EXPURGO_ENABLED
# no .env e deixe o job do scheduler rodar (ou chame o serviço com
# dry_run=False manualmente, com backup feito antes — hard delete é
# irreversível).
#
# Execução (container ejc_backend, na VPS):
#     docker exec -it ejc_backend python -m scripts.dry_run_expurgo_entrada
#     docker exec -it ejc_backend python -m scripts.dry_run_expurgo_entrada --dias 60
from __future__ import annotations

import argparse
import asyncio
import logging

from app.core.database import AsyncSessionLocal
from app.core.config import get_settings
from app.services.entrada_expurgo_service import expurgar_rascunhos_entrada_unica

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.dry_run_expurgo_entrada")


async def executar(dias: int) -> None:
    async with AsyncSessionLocal() as db:
        resultado = await expurgar_rascunhos_entrada_unica(db, dias=dias, dry_run=True)

    if "erro" in resultado:
        logger.error("[dry-run] expurgo falhou: %s", resultado["erro"])
        return

    logger.info(
        "[dry-run] janela de retenção: %d dia(s) (corte %s)",
        dias, resultado["corte"],
    )
    logger.info(
        "[dry-run] seriam removidos: %d batch(es), %d documento(s), "
        "%d byte(s) liberados",
        resultado["batches_removidos"], resultado["documentos_removidos"],
        resultado["bytes_liberados"],
    )
    if resultado["mais_antigo_dias"] is not None:
        logger.info(
            "[dry-run] rascunho abandonado mais antigo: %d dia(s)",
            resultado["mais_antigo_dias"],
        )
    logger.info(
        "[dry-run] NADA foi apagado. Para o modo real: ligue "
        "ENTRADA_EXPURGO_ENABLED=true no .env (job diário 03h50) — "
        "recomendado só após backup e revisão deste relatório."
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Dry-run do expurgo LGPD de rascunhos abandonados da "
                    "Entrada Única — só conta, nunca apaga.")
    ap.add_argument(
        "--dias", type=int, default=None,
        help="Janela de retenção em dias (default: ENTRADA_EXPURGO_DIAS do .env, 30).",
    )
    args = ap.parse_args()
    dias = args.dias if args.dias is not None else get_settings().ENTRADA_EXPURGO_DIAS
    asyncio.run(executar(dias))
