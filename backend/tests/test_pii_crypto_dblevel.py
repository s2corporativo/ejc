"""Conflito de interesses × PII cifrada — validação ROW-LEVEL (Bloco 6a).

Prova o caso que mais importa: um cliente cujo cpf/cnpj em texto puro JÁ FOI
removido (fase futura, pós-backfill completo) ainda é encontrado pela
checagem de conflito de interesses (EOAB arts. 34-35) através do cpf_hash —
a verificação ética não pode ter falso-negativo por causa da migração de PII.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_conflito_encontra_cliente_so_por_hash():
    """Simula um cliente JÁ MIGRADO: cpf em texto puro é NULL, só cpf_hash
    existe. detectar_conflito precisa achar mesmo assim."""
    from app.core.database import AsyncSessionLocal
    from app.services.conflito_service import detectar_conflito
    from app.services.pii_crypto import hash_documento, encrypt

    client_id = str(uuid4())
    cpf = "11122233344"
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO clients (id, tipo, nome, cpf, cpf_enc, cpf_hash, status) "
                "VALUES (:id, 'PF', 'Cliente Já Migrado', NULL, :enc, :hash, 'ativo')"
            ),
            {"id": client_id, "enc": encrypt(cpf), "hash": hash_documento(cpf)},
        )
        await db.commit()
        try:
            resultado = await detectar_conflito(db, cpf=cpf)
            ids_achados = {a["id"] for a in resultado["achados"] if a["tipo"] == "cliente_existente"}
            assert client_id in ids_achados, (
                "cliente com cpf em texto puro NULL (só hash) deveria ser "
                "encontrado pela checagem de conflito de interesses"
            )
        finally:
            await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
            await db.commit()


async def test_conflito_ainda_encontra_cliente_nao_migrado():
    """Contraprova: cliente ainda em texto puro (dual-write não aplicado, ou
    pré-Bloco 6a) continua funcionando como antes."""
    from app.core.database import AsyncSessionLocal
    from app.services.conflito_service import detectar_conflito

    client_id = str(uuid4())
    cpf = "55566677788"
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("INSERT INTO clients (id, tipo, nome, cpf, status) VALUES (:id, 'PF', 'Cliente Legado', :cpf, 'ativo')"),
            {"id": client_id, "cpf": cpf},
        )
        await db.commit()
        try:
            resultado = await detectar_conflito(db, cpf=cpf)
            ids_achados = {a["id"] for a in resultado["achados"] if a["tipo"] == "cliente_existente"}
            assert client_id in ids_achados
        finally:
            await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
            await db.commit()
