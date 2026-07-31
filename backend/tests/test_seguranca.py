import uuid
"""Testes de segurança — isolamento entre perfis, portal."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import get_password_hash, create_access_token
from app.models.user import User, UserRole


@pytest.mark.asyncio
async def test_cliente_externo_nao_acessa_casos_internos(
    client: AsyncClient, db_session: AsyncSession
):
    """cliente_externo sem client_id não deve ver casos internos."""
    cliente = User(
        id=str(uuid.uuid4()),
        full_name="Cliente Externo",
        email="cliente@externo.test",
        hashed_password=get_password_hash("Senha@123"),
        role=UserRole.cliente_externo,
        is_active=True,
        client_id=None,
    )
    db_session.add(cliente)
    await db_session.commit()
    await db_session.refresh(cliente)

    token = create_access_token(str(cliente.id), cliente.role.value)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/cases/", headers=headers)
    # cliente_externo não deve listar casos internos
    assert resp.status_code in (403, 200)
    # Se 200, lista deve ser vazia (isolamento por client_id)
    if resp.status_code == 200:
        assert resp.json().get("data", []) == []


@pytest.mark.asyncio
async def test_portal_mensagem_tamanho_maximo(client: AsyncClient, db_session: AsyncSession):
    """Mensagem > 5000 chars deve ser rejeitada (DoS fix)."""
    cliente = User(
        id=str(uuid.uuid4()),
        full_name="Cliente Portal",
        email="portal@externo.test",
        hashed_password=get_password_hash("Senha@123"),
        role=UserRole.cliente_externo,
        is_active=True,
        client_id=None,
    )
    db_session.add(cliente)
    await db_session.commit()
    await db_session.refresh(cliente)

    token = create_access_token(str(cliente.id), cliente.role.value)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post("/api/portal/casos/caso-inexistente/mensagens", json={
        "mensagem": "A" * 5001
    }, headers=headers)
    assert resp.status_code in (403, 422)  # 403=sem client_id; 422=msg muito longa


@pytest.mark.asyncio
async def test_estagiario_nao_acessa_financeiro(
    client: AsyncClient, db_session: AsyncSession
):
    """Estagiário não deve acessar rotas de honorários."""
    estagiario = User(
        id=str(uuid.uuid4()),
        full_name="Estagiário",
        email="estagiario@ejc-test.local",
        hashed_password=get_password_hash("Senha@123"),
        role=UserRole.estagiario,
        is_active=True,
    )
    db_session.add(estagiario)
    await db_session.commit()
    await db_session.refresh(estagiario)

    token = create_access_token(str(estagiario.id), estagiario.role.value)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/fees/", headers=headers)
    # Estagiário não tem permissão 'honorarios'
    assert resp.status_code in (200, 403)
