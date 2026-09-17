"""Regressões LGPD da anonimização sobre documentos de admissão (#1459).

Requer PostgreSQL de CI com migrations. Usa apenas dados fictícios.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (RUN_DB_TESTS=1)",
)


async def _criar_cliente(db, client_id: str):
    from app.services.pii_crypto import encrypt, hash_documento

    cpf = "39053344705"
    await db.execute(
        text(
            "INSERT INTO clients (id, tipo, nome, cpf_enc, cpf_hash, email, status) "
            "VALUES (:id, 'PF', 'Cliente Fictício LGPD', :cpf_enc, :cpf_hash, "
            ":email, 'ativo')"
        ),
        {
            "id": client_id,
            "cpf_enc": encrypt(cpf),
            "cpf_hash": hash_documento(cpf),
            "email": f"{client_id[:8]}@teste.local",
        },
    )


async def _criar_executor(db) -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Executor Fictício LGPD', 'socio', true)"
        ),
        {"id": uid, "email": f"exec-{uid[:8]}@teste.local"},
    )
    return uid


async def _criar_doc_admissao(db, client_id: str, status: str) -> str:
    doc_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO legal_docs "
            "(id, titulo, tipo_peca, status, conteudo, versao, ai_generated, "
            "human_reviewed, client_id, client_admission_kind) "
            "VALUES (:id, 'Procuração Cliente Fictício', 'procuracao', :status, "
            ":conteudo, 1, false, false, :cid, 'procuracao')"
        ),
        {
            "id": doc_id,
            "status": status,
            "conteudo": "Cliente Fictício, CPF 390.533.447-05, endereço fictício.",
            "cid": client_id,
        },
    )
    return doc_id


async def _limpar(db, client_id: str, executor_id: str, doc_id: str):
    await db.execute(text("DELETE FROM legal_docs WHERE id = :id"), {"id": doc_id})
    await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
    await db.execute(
        text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": executor_id}
    )
    await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": executor_id})
    await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def test_rascunho_admissao_e_redigido_e_soft_deleted_na_anonimizacao():
    from app.core.database import AsyncSessionLocal
    from app.services.client_anonimizacao import anonimizar_cliente

    client_id = str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        executor = await _criar_executor(db)
        doc_id = await _criar_doc_admissao(db, client_id, "rascunho")
        await db.commit()
        try:
            resultado = await anonimizar_cliente(
                db,
                client_id,
                executor_id=executor,
                executor_role="socio",
                motivo="teste automatizado",
            )
            assert resultado["documentos_admissao_anonimizados"] == 1

            doc = (await db.execute(
                text(
                    "SELECT titulo, conteudo, notas_revisao, deleted_at "
                    "FROM legal_docs WHERE id = :id"
                ),
                {"id": doc_id},
            )).mappings().one()
            assert doc["deleted_at"] is not None
            assert doc["conteudo"] == "[ANONIMIZADO — LGPD ART. 17]"
            assert "390.533.447-05" not in doc["conteudo"]
            assert "Cliente Fictício" not in doc["titulo"]
            assert doc["notas_revisao"] is None
        finally:
            await _limpar(db, client_id, executor, doc_id)


async def test_doc_admissao_final_bloqueia_inclusive_forcar_sem_apagar_pii():
    from app.core.database import AsyncSessionLocal
    from app.services.client_anonimizacao import anonimizar_cliente, verificar_bloqueios

    client_id = str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        executor = await _criar_executor(db)
        doc_id = await _criar_doc_admissao(db, client_id, "final")
        await db.commit()
        try:
            bloqueios = await verificar_bloqueios(db, client_id)
            assert any("documento(s) de admissão" in b for b in bloqueios)

            with pytest.raises(HTTPException) as exc:
                await anonimizar_cliente(
                    db,
                    client_id,
                    executor_id=executor,
                    executor_role="socio",
                    motivo="teste de override que não deve vencer retenção",
                    forcar=True,
                )
            assert exc.value.status_code == 409

            cliente = (await db.execute(
                text(
                    "SELECT cpf_enc, anonimizado_em FROM clients WHERE id = :id"
                ),
                {"id": client_id},
            )).mappings().one()
            assert cliente["cpf_enc"] is not None
            assert cliente["anonimizado_em"] is None

            conteudo = (await db.execute(
                text("SELECT conteudo FROM legal_docs WHERE id = :id"),
                {"id": doc_id},
            )).scalar_one()
            assert "390.533.447-05" in conteudo
        finally:
            await _limpar(db, client_id, executor, doc_id)
