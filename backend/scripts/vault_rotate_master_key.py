#!/usr/bin/env python3
"""
Rotação da CHAVE-MESTRA do Cofre de Credenciais (VAULT_MASTER_KEYS) — PR-6.

Re-encripta todas as linhas do cofre da chave-mestra ANTIGA para a NOVA, SEM
downtime e SEM expor segredo. NUNCA roda em migration/CI/deploy — só manual.

Como o MultiFernet funciona (ver app/services/vault_crypto.py): a PRIMEIRA
chave do CSV VAULT_MASTER_KEYS cifra; TODAS decifram. Isso torna a rotação um
processo em 3 passos, todos reversíveis até o último:

    (a) Operador GERA a chave nova e a coloca na FRENTE do CSV:
            VAULT_MASTER_KEYS=<NOVA>,<ANTIGA>
        A partir daí a app cifra o que for novo com a NOVA e ainda decifra o
        legado com a ANTIGA. Reinicie a app/worker para carregarem o CSV novo.

    (b) Roda ESTE script (--yes). Para cada linha com valor_encrypted não-nulo
        (ativa OU histórica) ele chama vault_crypto.rotacionar (MultiFernet.
        rotate: decifra com qualquer chave, recifra com a primária = NOVA) e
        persiste. Idempotente: rodar de novo não corrompe — o valor decifrado
        continua idêntico.

    (c) Só DEPOIS de (b) concluir sem erro, o operador REMOVE a ANTIGA do CSV:
            VAULT_MASTER_KEYS=<NOVA>
        e reinicia app/worker. A partir daí a antiga não decifra mais nada —
        por isso ela só sai quando NENHUM token depende mais dela.

Segurança:
  * Exige DUAS OU MAIS chaves no CSV. Com uma só não há o que rotacionar com
    segurança (você estaria recifrando com a mesma chave) — o script aborta e
    ensina o procedimento. Rode-o entre os passos (a) e (c).
  * Loga só PROGRESSO e CONTAGEM — nunca valores.
  * Só reescreve valor_encrypted. Não zera, não cria nem versiona nada.

USO:
    # 1) sempre rodar o dry-run primeiro (conta quantas linhas seriam
    #    rotacionadas; não grava nada):
    python scripts/vault_rotate_master_key.py --dry-run

    # 2) revisado o dry-run e com a chave nova já no CSV (passo (a)), efetivar:
    python scripts/vault_rotate_master_key.py --yes
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("ejc.cofre.rotacao")

_MSG_PROCEDIMENTO = (
    "VAULT_MASTER_KEYS tem MENOS de duas chaves — nada a rotacionar com "
    "segurança.\n"
    "Procedimento correto (ver docs/RUNBOOK_COFRE_CREDENCIAIS.md):\n"
    '  1. Gere a chave nova:\n'
    '       python -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())"\n'
    "  2. Coloque-a na FRENTE do CSV, mantendo a antiga:\n"
    "       VAULT_MASTER_KEYS=<NOVA>,<ANTIGA>\n"
    "     e reinicie app/worker.\n"
    "  3. Rode este script de novo (--dry-run e depois --yes).\n"
    "  4. Só então remova a antiga do CSV: VAULT_MASTER_KEYS=<NOVA>."
)


def _exigir_multiplas_chaves() -> int:
    """Aborta (SystemExit) se o CSV não tiver ao menos DUAS chaves.

    Retorna a quantidade de chaves quando o pré-requisito é satisfeito."""
    from app.services import vault_crypto

    n = len(vault_crypto.settings.vault_master_keys_list)
    if n < 2:
        raise SystemExit(_MSG_PROCEDIMENTO)
    return n


async def _rodar(dry_run: bool) -> None:
    from app.core.database import AsyncSessionLocal
    from app.services import credential_vault_service as svc

    n_chaves = _exigir_multiplas_chaves()
    logger.info(
        "VAULT_MASTER_KEYS: %d chave(s) no CSV; cifrando com a primária.",
        n_chaves,
    )

    async with AsyncSessionLocal() as db:
        rotacionadas, total = await svc.rotacionar_todas(db, dry_run=dry_run)
        if dry_run:
            logger.info(
                "[DRY-RUN] %d linha(s) com ciphertext seriam rotacionadas. "
                "Nada foi gravado. Rode com --yes para efetivar.",
                total,
            )
            return
        logger.info(
            "OK — %d de %d linha(s) rotacionada(s) para a chave primária atual. "
            "Concluído sem erro: agora você pode REMOVER a chave antiga do CSV "
            "(VAULT_MASTER_KEYS) e reiniciar app/worker.",
            rotacionadas, total,
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "--dry-run", action="store_true",
        help="Só conta quantas linhas seriam rotacionadas; não grava nada.",
    )
    grupo.add_argument(
        "--yes", action="store_true",
        help="Efetiva a rotação. Exige a chave nova já na FRENTE do CSV.",
    )
    args = parser.parse_args()
    asyncio.run(_rodar(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
