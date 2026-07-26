"""GET /clients/{client_id}/dossie — regressão do bug de coluna inexistente.

Bug real (auditoria funcional 2026-07-26): o endpoint fazia
`SELECT ... COALESCE(cpf, cnpj) AS cpf_cnpj FROM clients` em SQL cru. As
colunas `cpf`/`cnpj` em texto puro foram DROPADAS da tabela `clients` na
migration 112 (cutover C6/LGPD) — só existem cifradas (`cpf_enc`/`cnpj_enc`).
Toda chamada ao dossiê quebrava com
`asyncpg.exceptions.UndefinedColumnError: column "cpf" does not exist`
(mascarado como 500 genérico pela API). Reproduzido ao vivo contra Postgres
antes da correção.

A correção troca a busca do cliente para o ORM (`select(Client)`), usando a
property `Client.documento_plain` (decrypt sob demanda, PF-first) — mesmo
padrão já usado em routers/clients.py.

Postgres é OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: chama o handler
direto com `AsyncSessionLocal`). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "socio") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Dossie Teste', :role, true)"),
        {"id": uid, "email": f"dossie-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente_pf_com_cpf(db, nome: str, cpf: str) -> str:
    from app.services.pii_crypto import encrypt, hash_documento, normalizar_documento

    cid = str(uuid4())
    doc = normalizar_documento(cpf)
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status, cpf_enc, cpf_hash) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo', :cpf_enc, :cpf_hash)"),
        {
            "id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local",
            "cpf_enc": encrypt(doc), "cpf_hash": hash_documento(doc),
        },
    )
    return cid


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, user_ids=(), client_ids=()):
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    """Evita 'Event loop is closed' entre testes async (loop por função)."""
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_dossie_nao_quebra_com_coluna_cpf_inexistente_e_decifra_documento():
    from app.core.database import AsyncSessionLocal
    from app.routers.dossie_cliente import dossie_cliente

    tok = f"Zdc{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente_pf_com_cpf(db, f"Cliente Dossie {tok}", "111.444.777-35")
        await db.commit()
        try:
            resp = await dossie_cliente(cli, db, await _carregar_user(db, socio))
            assert resp["cliente"]["id"] == cli
            assert resp["cliente"]["cpf_cnpj"] == "11144477735"
            assert resp["resumo"]["total_casos"] == 0
        finally:
            await _limpar(db, user_ids=[socio], client_ids=[cli])


async def test_dossie_cliente_inexistente_404():
    from app.core.database import AsyncSessionLocal
    from app.routers.dossie_cliente import dossie_cliente

    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        try:
            with pytest.raises(HTTPException) as exc:
                await dossie_cliente(str(uuid4()), db, await _carregar_user(db, socio))
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, user_ids=[socio])


async def test_dossie_acesso_negado_para_nao_gestao():
    from app.core.database import AsyncSessionLocal
    from app.routers.dossie_cliente import dossie_cliente

    tok = f"Zde{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente_pf_com_cpf(db, f"Cliente Dossie Nego {tok}", "111.444.777-35")
        await db.commit()
        try:
            with pytest.raises(HTTPException) as exc:
                await dossie_cliente(cli, db, await _carregar_user(db, adv))
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, user_ids=[adv], client_ids=[cli])
