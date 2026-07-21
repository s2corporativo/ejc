"""Conflito de interesses × PII cifrada — validação ROW-LEVEL (cutover C6/LGPD).

Pós-migration 112 o cpf/cnpj em texto puro NÃO EXISTE MAIS: o documento vive só
cifrado (cpf_enc) e hasheado (cpf_hash). Prova o caso que mais importa: um
cliente assim ainda é encontrado pela checagem de conflito de interesses (EOAB
arts. 34-35) através do cpf_hash — a verificação ética não pode ter
falso-negativo por causa da criptografia de PII.
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
    from app.core.database import engine
    await engine.dispose()
    yield
    await engine.dispose()


async def test_conflito_encontra_cliente_so_por_hash():
    """Cliente com PII cifrada (só cpf_enc/cpf_hash, sem texto puro — a única
    realidade pós-migration 112): detectar_conflito precisa achar pelo hash."""
    from app.core.database import AsyncSessionLocal
    from app.services.conflito_service import detectar_conflito
    from app.services.pii_crypto import hash_documento, encrypt

    client_id = str(uuid4())
    cpf = "11122233344"
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO clients (id, tipo, nome, cpf_enc, cpf_hash, status) "
                "VALUES (:id, 'PF', 'Cliente Cifrado', :enc, :hash, 'ativo')"
            ),
            {"id": client_id, "enc": encrypt(cpf), "hash": hash_documento(cpf)},
        )
        await db.commit()
        try:
            resultado = await detectar_conflito(db, cpf=cpf)
            ids_achados = {a["id"] for a in resultado["achados"] if a["tipo"] == "cliente_existente"}
            assert client_id in ids_achados, (
                "cliente com cpf só cifrado (hash) deveria ser encontrado "
                "pela checagem de conflito de interesses"
            )
        finally:
            await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
            await db.commit()


# ── verificar_conflito (função POR TRÁS do endpoint /casos/verificar-conflito) ──
# Regressão do FALSO NEGATIVO: a checagem casa cpf/cnpj SOMENTE pelo índice cego
# (cpf_hash) — pós-cutover não há texto puro para escapar da checagem ética.

async def test_verificar_conflito_encontra_cliente_so_por_hash():
    """Cliente com PII cifrada (só cpf_hash) TEM de ser identificado como
    conflito crítico pelo verificar_conflito (endpoint)."""
    from app.core.database import AsyncSessionLocal
    from app.services.conflito_interesses import verificar_conflito
    from app.services.pii_crypto import hash_documento, encrypt

    client_id = str(uuid4())
    cpf = "22233344455"
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO clients (id, tipo, nome, cpf_enc, cpf_hash, status) "
                "VALUES (:id, 'PF', 'Parte Contrária Cifrada', :enc, :hash, 'ativo')"
            ),
            {"id": client_id, "enc": encrypt(cpf), "hash": hash_documento(cpf)},
        )
        await db.commit()
        try:
            resultado = await verificar_conflito(db, parte_contraria_doc=cpf)
            assert resultado["resultado"] == "conflito_identificado", (
                "cliente com PII cifrada (só hash) deveria disparar conflito "
                "crítico — verificação ética não pode ter falso-negativo"
            )
            tipos = {m["tipo"] for m in resultado["matches"]}
            assert "CLIENTE_ATIVO" in tipos
        finally:
            await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
            await db.commit()
