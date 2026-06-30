"""Testes de CRUD de casos juridicos."""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.client import Client, ClientTipo, ClientStatus


async def _criar_cliente(db: AsyncSession) -> str:
    c = Client(
        id=str(uuid.uuid4()),
        tipo=ClientTipo.PF,
        nome="Cliente Teste",
        status=ClientStatus.ativo,
    )
    db.add(c)
    await db.commit()
    return c.id


@pytest.mark.asyncio
async def test_criar_caso(client: AsyncClient, auth_headers, db_session: AsyncSession):
    cid = await _criar_cliente(db_session)
    resp = await client.post("/api/cases/", json={
        "titulo": "Acao de Cobranca Teste",
        "area": "civil",
        "client_id": cid,
    }, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["titulo"] == "Acao de Cobranca Teste"


@pytest.mark.asyncio
async def test_listar_casos(client: AsyncClient, auth_headers, db_session: AsyncSession):
    cid = await _criar_cliente(db_session)
    await client.post("/api/cases/", json={
        "titulo": "Caso Para Listar",
        "area": "trabalhista",
        "client_id": cid,
    }, headers=auth_headers)
    resp = await client.get("/api/cases/", headers=auth_headers)
    assert resp.status_code == 200
    assert "data" in resp.json()


@pytest.mark.asyncio
async def test_caso_nao_encontrado(client: AsyncClient, auth_headers):
    resp = await client.get("/api/cases/id-inexistente-99999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_criar_caso_sem_titulo(client: AsyncClient, auth_headers, db_session: AsyncSession):
    cid = await _criar_cliente(db_session)
    resp = await client.post("/api/cases/", json={"area": "civil", "client_id": cid}, headers=auth_headers)
    assert resp.status_code == 422
