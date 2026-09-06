# ── app/services/case_parte_pii.py ───────────────────────────────────────────
# Backfill idempotente do CPF/CNPJ das partes para as colunas cifradas
# (migration 159, achado DB-03 da auditoria de camadas de 06/09/2026).
#
# Por que mora aqui e não dentro da migration: a migration 112 (clients) fez o
# backfill em Python no próprio `upgrade()`, mas ela antecede a catraca do gate
# de deploy (`scripts/check_migration_compatibility.py`, ativa desde a 132),
# que reprova qualquer chamada fora de `op.*` em `upgrade()`. Fernet não é
# reproduzível em SQL, logo o backfill precisa ser código de aplicação —
# disparado por `python scripts/backfill_case_partes_pii.py` após o
# `alembic upgrade head` (o entrypoint faz isso) ou por quem operar o deploy.
#
# Contrato:
#   - toca SOMENTE linhas com `cpf_cnpj IS NOT NULL AND cpf_cnpj_enc IS NULL`
#     (texto puro sem cifra) — rodar N vezes é seguro;
#   - NÃO apaga o texto puro (o CONTRACT é migration futura, após os routers
#     de SQL cru migrarem para o hash);
#   - paginação por KEYSET (id > :last), não por OFFSET — as linhas tratadas
#     saem do predicado e um OFFSET pularia linhas (lição da 112);
#   - documento só-lixo (sem dígitos) não é cifrado: fica em claro e contado
#     em `ignoradas_sem_digitos`, para o relatório não fingir cobertura.
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

_LOTE = 500

_SQL_SELECT = text(
    "SELECT id, cpf_cnpj FROM case_partes "
    "WHERE id > :last AND cpf_cnpj IS NOT NULL AND cpf_cnpj_enc IS NULL "
    "ORDER BY id LIMIT :lim"
)
_SQL_UPDATE = text(
    "UPDATE case_partes SET cpf_cnpj_enc = :enc, cpf_cnpj_hash = :hash "
    "WHERE id = :id AND cpf_cnpj_enc IS NULL"
)


def _colunas_case_partes(conn) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns("case_partes")}


async def schema_pronto(db: AsyncSession) -> bool:
    """True se a migration 159 já criou as duas colunas cifradas (introspecção
    via inspector, sem SQL cru — o teste de paridade DR varre SQL cru do app)."""
    conn = await db.connection()
    colunas = await conn.run_sync(_colunas_case_partes)
    return {"cpf_cnpj_enc", "cpf_cnpj_hash"} <= colunas


async def backfill_case_partes_pii(db: AsyncSession, lote: int = _LOTE) -> dict:
    """Cifra + hasheia o texto puro das partes que ainda não têm cifra.

    Devolve contagens: {"cifradas": n, "ignoradas_sem_digitos": n,
    "lotes": n}. Commit por lote; a chamada é idempotente.
    """
    from app.services.pii_crypto import encrypt, hash_documento, normalizar_documento

    if not await schema_pronto(db):
        return {"cifradas": 0, "ignoradas_sem_digitos": 0, "lotes": 0,
                "motivo": "schema_sem_migration_159"}

    cifradas = 0
    ignoradas = 0
    lotes = 0
    last_id = ""  # '' precede qualquer id textual (comparação PG válida)
    while True:
        linhas = (await db.execute(_SQL_SELECT, {"last": last_id, "lim": lote})).fetchall()
        if not linhas:
            break
        lotes += 1
        for pid, doc in linhas:
            norm = normalizar_documento(doc)
            if norm:
                await db.execute(
                    _SQL_UPDATE,
                    {"id": pid, "enc": encrypt(norm), "hash": hash_documento(norm)},
                )
                cifradas += 1
            else:
                ignoradas += 1
            last_id = pid
        await db.commit()
    return {"cifradas": cifradas, "ignoradas_sem_digitos": ignoradas, "lotes": lotes}
