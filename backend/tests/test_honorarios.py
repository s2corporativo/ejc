"""Testes de honorários (fees)."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_listar_honorarios(client: AsyncClient, auth_headers):
    resp = await client.get("/api/fees/", headers=auth_headers)
    assert resp.status_code == 200
    assert "data" in resp.json()


@pytest.mark.asyncio
async def test_resumo_honorarios(client: AsyncClient, auth_headers):
    resp = await client.get("/api/fees/resumo", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "pendente" in data
    assert "atrasado" in data
    assert "recebido_mes" in data


@pytest.mark.asyncio
async def test_criar_honorario_invalido(client: AsyncClient, auth_headers):
    """Fee sem client_id deve ser rejeitado."""
    resp = await client.post("/api/fees/", json={"descricao": "sem cliente"}, headers=auth_headers)
    assert resp.status_code == 422
