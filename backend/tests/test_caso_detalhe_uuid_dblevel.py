"""GET /cases/{case_id}: separar path malformado (422) de caso inexistente (404).

Antes desta correção, `case_id` era comparado cru contra a coluna VARCHAR — um
path malformado ("abc") e um UUID válido mas inexistente respondiam o MESMO
404. O cliente não sabia se errou o formato do path ou se o caso não existe.

Nível de banco: o handler completo (`detalhe`) precisa rodar de ponta a ponta,
incluindo `_filtro_visibilidade`, para provar que o caminho feliz (UUID válido
e existente) não regride.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_advogado(db) -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, "
            "is_active) VALUES (:id, :email, 'x', 'Adv Teste', 'advogado', true)"
        ),
        {"id": uid, "email": f"uuid-{uid[:8]}@detalhe.local"},
    )
    return uid


async def _criar_cliente(db, nome: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) " "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@detalhe.local"},
    )
    return cid


async def _criar_caso(db, resp_id: str, client_id: str, titulo: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id, advogado_responsavel_id) "
            "VALUES (:id, :tit, 'civil', 'em_instrucao', :cli, :resp)"
        ),
        {"id": cid, "tit": titulo, "cli": client_id, "resp": resp_id},
    )
    return cid


async def _limpar(db, *, case_ids=(), client_ids=(), user_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def _carregar_user(db, uid: str):
    from app.models.user import User
    from sqlalchemy import select

    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


@pytest.mark.parametrize("malformado", ["abc", "123", "' OR '1'='1"])
async def test_case_id_malformado_e_422_nao_404(malformado):
    """Regressão direta: antes, isto caía na consulta e virava 404 igual a um
    UUID válido inexistente."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import detalhe

    async with AsyncSessionLocal() as db:
        adv = await _criar_advogado(db)
        await db.commit()
        try:
            user = await _carregar_user(db, adv)
            with pytest.raises(HTTPException) as exc:
                await detalhe(case_id=malformado, db=db, cu=user)
            assert exc.value.status_code == 422
        finally:
            await _limpar(db, user_ids=[adv])


async def test_uuid_valido_mas_inexistente_continua_404():
    """O contrato de "não existe" não pode mudar — só o de "formato errado"."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import detalhe

    async with AsyncSessionLocal() as db:
        adv = await _criar_advogado(db)
        await db.commit()
        try:
            user = await _carregar_user(db, adv)
            with pytest.raises(HTTPException) as exc:
                await detalhe(case_id=str(uuid4()), db=db, cu=user)
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, user_ids=[adv])


async def test_uuid_valido_e_existente_chega_como_string_ao_handler():
    """Critério da Issue: UUID bem formado continua chegando como STRING —
    não pode virar `uuid.UUID` no meio do caminho e quebrar a comparação com a
    coluna VARCHAR."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import detalhe

    async with AsyncSessionLocal() as db:
        adv = await _criar_advogado(db)
        cli = await _criar_cliente(db, "Cliente do teste de UUID")
        caso = await _criar_caso(db, adv, cli, "Caso do teste de UUID")
        await db.commit()
        try:
            user = await _carregar_user(db, adv)
            resultado = await detalhe(case_id=caso, db=db, cu=user)
            assert resultado.titulo == "Caso do teste de UUID"
        finally:
            await _limpar(db, case_ids=[caso], client_ids=[cli], user_ids=[adv])
