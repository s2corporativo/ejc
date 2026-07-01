import uuid
"""
Testes do cluster de correções IDOR/role-gate (auditoria 2026-06-30).

Cobre os NOVOS gates de autorização adicionados aos endpoints que antes
expunham dados de qualquer cliente a qualquer perfil interno:
  A9  — GET /api/data-room-v4/            (estagiário/secretaria/financeiro: 403)
  A11 — GET /api/inadimplencia/alertas    (só gestão/financeiro)
  A14 — POST /api/clients/verificar-conflito (só perfis de gestão de clientes)

O núcleo `verificar_acesso_caso` (reusado por A8/A12/C4) já é coberto por
tests/test_ownership.py. Estes testes validam que o gate de PAPEL bloqueia o
perfil errado (403) e libera o perfil correto (2xx). Suíte de integração:
roda na CI com Postgres (ejc_test).
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import text

from app.core.security import get_password_hash, create_access_token
from app.models.user import User, UserRole

# inadimplencia_alerts é criada por SQL cru na migração 050 (sem modelo ORM),
# logo o create_all do conftest não a cria. Este DDL replica as colunas lidas
# por listar_alertas para o teste positivo (financeiro) render 200 real.
_DDL_INADIMPLENCIA = """
    CREATE TABLE IF NOT EXISTS inadimplencia_alerts (
        id varchar(36) PRIMARY KEY,
        fee_id varchar(36),
        case_id varchar(36),
        client_id varchar(36),
        days_overdue integer NOT NULL DEFAULT 0,
        amount_due numeric(12,2) NOT NULL DEFAULT 0,
        alert_level varchar(30),
        action_taken text,
        resolved boolean NOT NULL DEFAULT false,
        created_at timestamptz DEFAULT now()
    )
"""


async def _mk_user(db: AsyncSession, role: UserRole) -> User:
    u = User(
        id=str(uuid.uuid4()),
        full_name=f"TESTE_EJC {role.value}",
        email=f"teste_ejc_{role.value}_{uuid.uuid4().hex[:6]}@ejctest.com",
        hashed_password=get_password_hash("Senha@123"),
        role=role,
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _h(u: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role.value)}"}


# ── A11 — inadimplência só para gestão/financeiro ─────────────────────────────
@pytest.mark.asyncio
async def test_inadimplencia_estagiario_bloqueado(client: AsyncClient, db_session):
    u = await _mk_user(db_session, UserRole.estagiario)
    resp = await client.get("/api/inadimplencia/alertas", headers=_h(u))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_inadimplencia_financeiro_liberado(client: AsyncClient, db_session):
    await db_session.execute(text(_DDL_INADIMPLENCIA))
    await db_session.commit()
    u = await _mk_user(db_session, UserRole.financeiro)
    resp = await client.get("/api/inadimplencia/alertas", headers=_h(u))
    assert resp.status_code == 200


# ── A14 — verificar-conflito só para quem gerencia clientes ───────────────────
@pytest.mark.asyncio
async def test_conflito_estagiario_bloqueado(client: AsyncClient, db_session):
    u = await _mk_user(db_session, UserRole.estagiario)
    resp = await client.post(
        "/api/clients/verificar-conflito",
        headers=_h(u),
        json={"nome": "TESTE_EJC Parte"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_conflito_advogado_liberado(client: AsyncClient, db_session):
    u = await _mk_user(db_session, UserRole.advogado)
    resp = await client.post(
        "/api/clients/verificar-conflito",
        headers=_h(u),
        json={"nome": "TESTE_EJC Parte"},
    )
    assert resp.status_code == 200


# ── A9 — listar data rooms não exposto a perfis não-jurídicos ─────────────────
@pytest.mark.asyncio
async def test_data_room_v4_estagiario_bloqueado(client: AsyncClient, db_session):
    u = await _mk_user(db_session, UserRole.estagiario)
    resp = await client.get("/api/data-room-v4/", headers=_h(u))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_data_room_v4_advogado_liberado(client: AsyncClient, db_session):
    u = await _mk_user(db_session, UserRole.advogado)
    resp = await client.get("/api/data-room-v4/", headers=_h(u))
    assert resp.status_code == 200
