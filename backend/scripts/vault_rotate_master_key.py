#!/usr/bin/env python
# ── scripts/vault_rotate_master_key.py ───────────────────────────────────────
# Rotação da chave-mestra do Cofre de Credenciais (PR-6 do
# docs/PLANO_COFRE_CREDENCIAIS.md).
#
# O `docs/RUNBOOK_COFRE_CREDENCIAIS.md` e a docstring de
# `credential_vault_service.rotacionar_todas` já apontavam para este script,
# e ele não existia: o procedimento de rotação — que é resposta a incidente —
# estava documentado sem ponto de entrada.
#
# O que faz: chama `rotacionar_todas`, que roda `vault_crypto.rotacionar`
# (MultiFernet.rotate: decifra com QUALQUER chave do CSV, recifra com a
# primária) em cada linha do cofre que ainda guarda ciphertext, ativa ou
# histórica. Idempotente: o valor decifrado nunca muda.
#
# Sequência operacional (a ordem importa):
#   1. PREPEND da chave nova em VAULT_MASTER_KEYS, mantendo a antiga no CSV;
#   2. este script com --dry-run (conta, não grava);
#   3. este script com --yes (efetiva);
#   4. só então remover a chave antiga do CSV.
#
# Rede de segurança: com menos de duas chaves no CSV não há rotação possível
# (o passo 1 não foi feito) e o script recusa antes de tocar no banco — mesma
# recusa que `rotacionar_todas` faz do outro lado.
#
# Execução (container ejc_backend, na VPS):
#     docker exec -it ejc_backend python -m scripts.vault_rotate_master_key --dry-run
#     docker exec -it ejc_backend python -m scripts.vault_rotate_master_key --yes
from __future__ import annotations

import argparse
import asyncio
import logging

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.services.credential_vault_service import rotacionar_todas

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.vault_rotate_master_key")


def _validar_chaves(dry_run: bool) -> bool:
    """Recusa quando o PREPEND da chave nova ainda não foi feito."""
    chaves = get_settings().vault_master_keys_list
    if not chaves:
        logger.error(
            "VAULT_MASTER_KEYS vazia: o cofre não é operável e não há o que "
            "rotacionar. Defina a variável no .env antes de continuar."
        )
        return False
    if len(chaves) < 2:
        logger.error(
            "VAULT_MASTER_KEYS tem só 1 chave. A rotação pressupõe a chave NOVA "
            "no início do CSV e a ANTIGA ainda presente, para o MultiFernet "
            "decifrar o legado. Faça o PREPEND da chave nova e rode de novo.\n"
            "Ver docs/RUNBOOK_COFRE_CREDENCIAIS.md."
        )
        return False
    logger.info(
        "%d chaves em VAULT_MASTER_KEYS; recifrando com a primária%s.",
        len(chaves),
        " (dry-run)" if dry_run else "",
    )
    return True


async def executar(dry_run: bool) -> int:
    if not _validar_chaves(dry_run):
        return 2

    async with AsyncSessionLocal() as db:
        rotacionadas, total = await rotacionar_todas(db, dry_run=dry_run)

    if dry_run:
        logger.info(
            "[dry-run] %d linha(s) com ciphertext seriam recifradas. Nada foi gravado.",
            total,
        )
        logger.info("Para efetivar: python -m scripts.vault_rotate_master_key --yes")
        return 0

    logger.info("%d de %d linha(s) recifradas com a chave primária.", rotacionadas, total)
    logger.info(
        "Confira o acesso às integrações e só então remova a chave antiga de "
        "VAULT_MASTER_KEYS (passo 4 do runbook)."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rotação da chave-mestra do Cofre de Credenciais do EJC.",
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "--dry-run",
        action="store_true",
        help="Conta as linhas candidatas sem gravar nada.",
    )
    grupo.add_argument(
        "--yes",
        action="store_true",
        help="Efetiva a rotação (recifra e persiste).",
    )
    args = parser.parse_args()
    return asyncio.run(executar(dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
