#!/usr/bin/env python3
"""
Backfill de criptografia de PII (CPF/CNPJ) — LGPD, Bloco 6a.

NUNCA roda automaticamente. Não faz parte de nenhuma migration, CI ou deploy.
Só executa quando invocado manualmente, com confirmação explícita.

O QUE FAZ: para cada Client com cpf/cnpj em texto puro e cpf_hash/cnpj_hash
ainda vazios, calcula e grava cpf_enc/cnpj_enc/cpf_hash/cnpj_hash — SEM tocar
nas colunas cpf/cnpj em texto puro (elas continuam existindo até uma decisão
futura, separada, de removê-las). Idempotente: rodar de novo não duplica nem
sobrescreve linhas já migradas.

PRÉ-REQUISITOS (o script verifica e recusa rodar sem):
1. Backup do banco feito e validado — o script NÃO faz backup sozinho.
2. PII_ENCRYPTION_KEY e PII_HASH_KEY definidas no ambiente (as mesmas que a
   aplicação vai usar para decifrar depois — trocar a chave depois inutiliza
   os dados cifrados com a anterior).
3. Confirmação explícita via flag --confirmar (não roda em modo dry-run
   silencioso por padrão — mostra sempre um --dry-run primeiro).

USO:
    # 1) sempre rodar dry-run primeiro (não grava nada, só relata quantos
    #    clientes seriam afetados):
    python scripts/backfill_pii_encryption.py --dry-run

    # 2) com backup confirmado e revisão do dry-run, aplicar de fato:
    python scripts/backfill_pii_encryption.py --confirmar
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def _rodar(dry_run: bool) -> None:
    from app.core.config import get_settings
    from app.core.database import AsyncSessionLocal
    from app.models.client import Client
    from app.services.pii_crypto import normalizar_documento, encrypt, hash_documento
    from sqlalchemy import select, or_

    settings = get_settings()
    if not settings.PII_ENCRYPTION_KEY or not settings.PII_HASH_KEY:
        print(
            "ERRO: PII_ENCRYPTION_KEY e/ou PII_HASH_KEY não definidas no ambiente.\n"
            "Defina-as no .env ANTES de rodar — são as chaves que a aplicação vai "
            "usar para decifrar depois do backfill."
        )
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        clientes = (await db.execute(
            select(Client).where(
                Client.deleted_at.is_(None),
                Client.anonimizado_em.is_(None),
                or_(Client.cpf.is_not(None), Client.cnpj.is_not(None)),
                or_(Client.cpf_hash.is_(None), Client.cnpj_hash.is_(None)),
            )
        )).scalars().all()

        # Só considera quem realmente tem cpf/cnpj sem o par _hash correspondente.
        pendentes = [
            c for c in clientes
            if (c.cpf and not c.cpf_hash) or (c.cnpj and not c.cnpj_hash)
        ]

        print(f"Clientes pendentes de backfill: {len(pendentes)}")
        if dry_run:
            print("(--dry-run: nada foi gravado. Rode com --confirmar para aplicar.)")
            return
        if not pendentes:
            print("Nada a fazer.")
            return

        for c in pendentes:
            cpf_norm = normalizar_documento(c.cpf)
            cnpj_norm = normalizar_documento(c.cnpj)
            if cpf_norm and not c.cpf_hash:
                c.cpf_enc = encrypt(cpf_norm)
                c.cpf_hash = hash_documento(cpf_norm)
            if cnpj_norm and not c.cnpj_hash:
                c.cnpj_enc = encrypt(cnpj_norm)
                c.cnpj_hash = hash_documento(cnpj_norm)
        await db.commit()
        print(f"OK — {len(pendentes)} cliente(s) migrado(s).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--dry-run", action="store_true", help="Só relata, não grava nada.")
    grupo.add_argument("--confirmar", action="store_true", help="Aplica de fato. Requer backup prévio feito por você.")
    args = parser.parse_args()

    if args.confirmar:
        resposta = input(
            "\nATENÇÃO: isto grava cpf_enc/cnpj_enc/cpf_hash/cnpj_hash em produção.\n"
            "Você já fez backup do banco e validou que consegue restaurar? "
            "Digite exatamente SIM para continuar: "
        )
        if resposta.strip() != "SIM":
            print("Cancelado — resposta diferente de 'SIM'.")
            sys.exit(1)

    asyncio.run(_rodar(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
