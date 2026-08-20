"""Regressão LGPD: clientes homônimos nunca compartilham peças de admissão."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

RUN_DB_TESTS = bool(os.getenv("RUN_DB_TESTS"))
pytestmark = pytest.mark.skipif(not RUN_DB_TESTS, reason="requer banco (RUN_DB_TESTS=1)")

if RUN_DB_TESTS:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.client import Client, ClientTipo
    from app.models.legal_doc import LegalDoc
    from app.models.user import User, UserRole
    from app.services.geracao_documental_cliente import (
        gerar_documentos_cliente,
        listar_pecas_cliente,
    )


def _cliente(db: AsyncSession, nome: str) -> Client:
    cli = Client(id=str(uuid4()), tipo=ClientTipo.PF, nome=nome)
    cli.cidade = "Betim"
    cli.estado = "MG"
    db.add(cli)
    return cli


def _advogado(db: AsyncSession) -> User:
    uid = str(uuid4())
    user = User(
        id=uid,
        full_name="Advogado Teste Isolamento",
        email=f"isolamento-{uid[:8]}@ejc-homologacao.com",
        hashed_password="$2b$12$placeholderhashplaceholderhashplaceholderhashpl",
        role=UserRole.advogado,
        is_active=True,
    )
    db.add(user)
    return user


@pytest.mark.asyncio
async def test_clientes_homonimos_possuem_documentos_distintos_por_client_id():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        nome_igual = f"Cliente Homonimo {uuid4().hex[:8]}"
        cliente_a = _cliente(db, nome_igual)
        cliente_b = _cliente(db, nome_igual)
        advogado = _advogado(db)
        await db.commit()

        gerado_a = await gerar_documentos_cliente(db, cliente_a, advogado)
        gerado_b = await gerar_documentos_cliente(db, cliente_b, advogado)

        ids_a = {
            gerado_a["procuracao"]["legal_doc_id"],
            gerado_a["contrato"]["legal_doc_id"],
        }
        ids_b = {
            gerado_b["procuracao"]["legal_doc_id"],
            gerado_b["contrato"]["legal_doc_id"],
        }
        assert ids_a.isdisjoint(ids_b)

        docs = (
            await db.execute(select(LegalDoc).where(LegalDoc.id.in_(ids_a | ids_b)))
        ).scalars().all()
        por_id = {doc.id: doc for doc in docs}
        assert all(por_id[doc_id].client_id == cliente_a.id for doc_id in ids_a)
        assert all(por_id[doc_id].client_id == cliente_b.id for doc_id in ids_b)

        lista_a = await listar_pecas_cliente(db, cliente_a)
        lista_b = await listar_pecas_cliente(db, cliente_b)
        assert {item["id"] for item in lista_a} == ids_a
        assert {item["id"] for item in lista_b} == ids_b

        repetido_b = await gerar_documentos_cliente(db, cliente_b, advogado)
        assert repetido_b["ja_existia"] is True
        assert repetido_b["procuracao"]["legal_doc_id"] in ids_b
        assert repetido_b["contrato"]["legal_doc_id"] in ids_b
        assert repetido_b["procuracao"]["legal_doc_id"] not in ids_a
        assert repetido_b["contrato"]["legal_doc_id"] not in ids_a

        await db.rollback()
