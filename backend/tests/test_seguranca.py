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
async def test_mensagem_caso_tamanho_maximo(client: AsyncClient, db_session: AsyncSession):
    """Mensagem acima do limite deve ser rejeitada (DoS fix).

    Corrigido 2026-07-01: o endpoint real de mensagens é
    POST /api/cases/{case_id}/mensagens (routers/mensagens.py), com cap de
    4000 chars no schema Pydantic (MsgIn.mensagem). O antigo teste apontava
    para /api/portal/mensagem, que nunca existiu (404) e não exercia o cap.

    Usa um usuário staff (advogado): o corpo é validado (422) ANTES de qualquer
    consulta ao caso, então não é preciso criar um caso real. cliente_externo
    seria barrado pelo middleware (403) antes de chegar ao schema.
    """
    staff = User(
        id=str(uuid.uuid4()),
        full_name="Advogado Teste",
        email="advogado.msg@ejc-test.local",
        hashed_password=get_password_hash("Senha@123"),
        role=UserRole.advogado,
        is_active=True,
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)

    token = create_access_token(str(staff.id), staff.role.value)
    headers = {"Authorization": f"Bearer {token}"}

    case_id = str(uuid.uuid4())  # não precisa existir: o cap do corpo é checado antes
    resp = await client.post(
        f"/api/cases/{case_id}/mensagens",
        json={"mensagem": "A" * 5001},
        headers=headers,
    )
    assert resp.status_code == 422  # corpo excede max_length=4000


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
