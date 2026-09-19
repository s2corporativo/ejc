#!/usr/bin/env python3
"""Saneia PII legado em case_partes sem expor valores sensíveis.

Uso seguro:
  python -m scripts.backfill_case_partes_pii              # dry-run
  PII_BACKFILL_ALLOW=1 python -m scripts.backfill_case_partes_pii --apply

Garantias:
- não imprime CPF/CNPJ, e-mail, telefone nem IDs de partes;
- aplica tudo em uma única transação com SELECT ... FOR UPDATE;
- valida ciphertext já existente antes de apagar plaintext;
- grava AuditLog apenas com contagens, nunca com PII;
- falha fechado se restar qualquer plaintext após o backfill.
"""
from __future__ import annotations

import argparse
import json
import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.services.pii_crypto import decrypt, encrypt, hash_documento, normalizar_documento

settings = get_settings()


def _database_url() -> str:
    return (
        (os.getenv("PII_BACKFILL_DATABASE_URL") or "").strip()
        or (os.getenv("DATABASE_URL_SYNC") or "").strip()
        or settings.DATABASE_URL_SYNC
    )


def _limpo(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _validar_ou_cifrar(
    *,
    legado: str | None,
    ciphertext: str | None,
    normalizar: bool = False,
) -> str | None:
    """Retorna ciphertext seguro; se já existe, exige equivalência com legado."""
    legado_limpo = _limpo(legado)
    if not legado_limpo:
        return ciphertext

    esperado = normalizar_documento(legado_limpo) if normalizar else legado_limpo
    if not esperado:
        # Um documento legado não vazio que não pode ser normalizado não pode ser
        # descartado silenciosamente. Falha fechado para preservar o dado original
        # e permitir saneamento/quarentena manual antes de uma nova execução.
        if normalizar:
            raise RuntimeError(
                "documento legado não pôde ser normalizado; "
                "operação abortada sem commit"
            )
        return ciphertext

    if ciphertext:
        atual = decrypt(ciphertext)
        atual_cmp = normalizar_documento(atual) if normalizar else _limpo(atual)
        if atual_cmp != esperado:
            raise RuntimeError(
                "PII legado diverge do ciphertext existente; operação abortada sem commit"
            )
        return ciphertext

    return encrypt(legado_limpo)


def _contar_plaintext(conn) -> int:
    return int(
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM case_partes
                WHERE cpf_cnpj IS NOT NULL
                   OR email IS NOT NULL
                   OR telefone IS NOT NULL
                """
            )
        ).scalar_one()
    )


def executar(*, aplicar: bool) -> dict[str, int | bool]:
    engine = create_engine(_database_url(), pool_pre_ping=True, future=True)
    try:
        with engine.begin() as conn:
            if aplicar:
                if os.getenv("PII_BACKFILL_ALLOW") != "1":
                    raise RuntimeError(
                        "PII_BACKFILL_ALLOW=1 é obrigatório para aplicar o saneamento"
                    )
                # SHARE ROW EXCLUSIVE conflita com ROW EXCLUSIVE (DML):
                # impede INSERT/UPDATE/DELETE concorrentes sem bloquear leituras.
                conn.execute(
                    text("LOCK TABLE case_partes IN SHARE ROW EXCLUSIVE MODE")
                )

            antes = _contar_plaintext(conn)
            rows = conn.execute(
                text(
                    """
                    SELECT id, cpf_cnpj, cpf_cnpj_enc, cpf_cnpj_hash,
                           email, email_enc, telefone, telefone_enc
                    FROM case_partes
                    WHERE cpf_cnpj IS NOT NULL
                       OR email IS NOT NULL
                       OR telefone IS NOT NULL
                    FOR UPDATE
                    """
                )
            ).mappings().all()

            if not aplicar:
                return {
                    "aplicar": False,
                    "linhas_com_plaintext": antes,
                    "linhas_atualizadas": 0,
                    "plaintext_restante": antes,
                }

            atualizadas = 0
            for row in rows:
                cpf_enc = _validar_ou_cifrar(
                    legado=row["cpf_cnpj"],
                    ciphertext=row["cpf_cnpj_enc"],
                    normalizar=True,
                )
                cpf_norm = normalizar_documento(_limpo(row["cpf_cnpj"]))
                cpf_hash = row["cpf_cnpj_hash"]
                if cpf_norm:
                    calculado = hash_documento(cpf_norm)
                    if cpf_hash and cpf_hash != calculado:
                        raise RuntimeError(
                            "hash de documento legado diverge do valor observado; "
                            "operação abortada sem commit"
                        )
                    cpf_hash = calculado

                email_enc = _validar_ou_cifrar(
                    legado=row["email"],
                    ciphertext=row["email_enc"],
                )
                telefone_enc = _validar_ou_cifrar(
                    legado=row["telefone"],
                    ciphertext=row["telefone_enc"],
                )

                conn.execute(
                    text(
                        """
                        UPDATE case_partes
                           SET cpf_cnpj_enc = :cpf_enc,
                               cpf_cnpj_hash = :cpf_hash,
                               email_enc = :email_enc,
                               telefone_enc = :telefone_enc,
                               cpf_cnpj = NULL,
                               email = NULL,
                               telefone = NULL,
                               updated_at = NOW()
                         WHERE id = :id
                        """
                    ),
                    {
                        "id": row["id"],
                        "cpf_enc": cpf_enc,
                        "cpf_hash": cpf_hash,
                        "email_enc": email_enc,
                        "telefone_enc": telefone_enc,
                    },
                )
                atualizadas += 1

            restante = _contar_plaintext(conn)
            if restante:
                raise RuntimeError(
                    "gate LGPD falhou: ainda existem linhas com PII plaintext"
                )

            conn.execute(
                text(
                    """
                    INSERT INTO audit_logs (
                        id, user_id, user_role, ip, acao, entidade, registro_id,
                        dados_antes, dados_depois, detalhes
                    )
                    VALUES (
                        :id, NULL, 'system', NULL, 'PII_BACKFILL', 'case_partes',
                        NULL, CAST(:antes AS jsonb), CAST(:depois AS jsonb),
                        'Saneamento transacional de PII legado; valores sensíveis não registrados.'
                    )
                    """
                ),
                {
                    "id": str(uuid4()),
                    "antes": json.dumps({"linhas_com_plaintext": antes}),
                    "depois": json.dumps(
                        {
                            "linhas_atualizadas": atualizadas,
                            "plaintext_restante": restante,
                        }
                    ),
                },
            )

            return {
                "aplicar": True,
                "linhas_com_plaintext": antes,
                "linhas_atualizadas": atualizadas,
                "plaintext_restante": restante,
            }
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="aplica o saneamento; sem esta flag, apenas conta linhas afetadas",
    )
    args = parser.parse_args()

    resultado = executar(aplicar=args.apply)
    print(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
