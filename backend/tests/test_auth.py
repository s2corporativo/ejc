"""Testes de autenticação."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_sucesso(client: AsyncClient, admin_user):
    """Login com credenciais corretas retorna access_token."""
    resp = await client.post("/api/auth/login", json={
        "email": "admin@ejctest.com",
        "password": "Senha@123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_senha_errada(client: AsyncClient, admin_user):
    """Login com senha errada retorna 401."""
    resp = await client.post("/api/auth/login", json={
        "email": "admin@ejctest.com",
        "password": "SenhaErrada",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_usuario_inexistente(client: AsyncClient):
    """Login com email inexistente retorna 401."""
    resp = await client.post("/api/auth/login", json={
        "email": "fantasma@gmail.com",
        "password": "qualquer",
    })
    assert resp.status_code in (401, 404)


@pytest.mark.asyncio
async def test_rota_protegida_sem_token(client: AsyncClient):
    """Rota protegida sem Bearer retorna 401 ou 403."""
    resp = await client.get("/api/cases/")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_rota_protegida_token_invalido(client: AsyncClient):
    """Token malformado retorna 401 ou 403."""
    resp = await client.get("/api/cases/", headers={"Authorization": "Bearer token_invalido"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_calendar_url(client: AsyncClient, auth_headers):
    """GET /users/me/calendar-url com token válido retorna URL ou None."""
    resp = await client.get("/api/users/me/calendar-url", headers=auth_headers)
    assert resp.status_code == 200
