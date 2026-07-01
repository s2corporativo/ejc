import uuid
"""
Testes de POST/GET /api/portal/casos/{case_id}/mensagens (chat cliente↔escritório).

Corrige o bug em que o cliente_externo não conseguia enviar mensagem pelo
portal: o frontend postava em /api/cases/{id}/mensagens, mas o auth_middleware
só libera cliente_externo em /api/portal/* (403 sempre). Os novos endpoints
vivem sob /api/portal e reusam a tabela portal_mensagens.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, create_access_token
from app.models.user import User, UserRole
from app.models.client import Client, ClientTipo
from app.models.case import Case, CaseArea


async def _mk_cliente_externo(db: AsyncSession, client_id: str) -> User:
    u = User(
        id=str(uuid.uuid4()),
        full_name="TESTE_EJC Cliente Portal",
        email=f"teste_ejc_portal_{uuid.uuid4().hex[:6]}@ejctest.com",
        hashed_password=get_password_hash("Senha@123"),
        role=UserRole.cliente_externo,
        is_active=True,
        client_id=client_id,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_client_e_caso(db: AsyncSession) -> tuple[str, str]:
    cli = Client(id=str(uuid.uuid4()), tipo=ClientTipo.PF, nome="TESTE_EJC Cliente")
    db.add(cli)
    await db.flush()
    caso = Case(
        id=str(uuid.uuid4()), titulo="TESTE_EJC Caso", area=CaseArea.civil,
        client_id=cli.id,
    )
    db.add(caso)
    await db.commit()
    return cli.id, caso.id


def _h(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role.value)}"}


@pytest.mark.asyncio
async def test_cliente_envia_e_le_mensagem_do_proprio_caso(
    client: AsyncClient, db_session: AsyncSession
):
    client_id, case_id = await _mk_client_e_caso(db_session)
    u = await _mk_cliente_externo(db_session, client_id)

    resp = await client.post(
        f"/api/portal/casos/{case_id}/mensagens",
        json={"mensagem": "Olá, gostaria de saber do andamento."},
        headers=_h(u),
    )
    assert resp.status_code == 201, resp.text

    resp2 = await client.get(f"/api/portal/casos/{case_id}/mensagens", headers=_h(u))
    assert resp2.status_code == 200
    msgs = resp2.json()
    assert len(msgs) == 1
    assert msgs[0]["autor_tipo"] == "cliente"


@pytest.mark.asyncio
async def test_cliente_nao_acessa_mensagens_de_caso_alheio(
    client: AsyncClient, db_session: AsyncSession
):
    _client_id_dono, case_id = await _mk_client_e_caso(db_session)
    _outro_client_id, _ = await _mk_client_e_caso(db_session)
    intruso = await _mk_cliente_externo(db_session, _outro_client_id)

    resp = await client.post(
        f"/api/portal/casos/{case_id}/mensagens",
        json={"mensagem": "Tentativa de acesso indevido"},
        headers=_h(intruso),
    )
    assert resp.status_code == 404  # isolamento: caso não é do seu client_id


@pytest.mark.asyncio
async def test_mensagem_portal_tamanho_maximo(client: AsyncClient, db_session: AsyncSession):
    client_id, case_id = await _mk_client_e_caso(db_session)
    u = await _mk_cliente_externo(db_session, client_id)

    resp = await client.post(
        f"/api/portal/casos/{case_id}/mensagens",
        json={"mensagem": "A" * 4001},
        headers=_h(u),
    )
    assert resp.status_code == 422
