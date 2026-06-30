"""Testes de prazos processuais."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_listar_prazos(client: AsyncClient, auth_headers):
    resp = await client.get("/api/deadlines/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body


@pytest.mark.asyncio
async def test_criar_prazo_invalido(client: AsyncClient, auth_headers):
    """Prazo sem campos obrigatórios deve ser rejeitado."""
    resp = await client.post("/api/deadlines/", json={}, headers=auth_headers)
    assert resp.status_code == 422
