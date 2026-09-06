"""CRM — criação de LEAD pelo funil (correção de auditoria funcional).

Antes: `ClientCreate` não tinha status/etapa_funil/origem_lead/area_interesse
(o Pydantic descartava) e todo lead do board nascia `ativo` — sumia do funil
(GET /clients/?status=lead vazio) e poluía a lista de clientes ativos.

Cobre (handlers diretos com AsyncSessionLocal, padrão *_dblevel.py):
  - POST /clients/ com status="lead" + etapa_funil/origem_lead/area_interesse
    → persiste lead e o board (GET ?status=lead) o devolve com etapa preenchida;
  - lead criado sem etapa_funil explícita → default "lead" (board agrupa por etapa);
  - PATCH etapa_funil (drag do board) persiste; conversão (status=ativo) tira do funil;
  - cliente comum criado sem status → continua "ativo" (comportamento preservado);
  - status/etapa_funil inválidos → rejeitados pela validação Pydantic (422).

Postgres OBRIGATÓRIO (migrations aplicadas). Sem RUN_DB_TESTS=1, pula.
Dados 100% fictícios.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.schemas.client import ClientCreate, ClientUpdate

from _limpeza_cliente import limpar_dependencias_de_clientes

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'CRM Teste', :role, true)"),
        {"id": uid, "email": f"crm-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _carregar_user(db, uid: str):
    from sqlalchemy import select
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, client_ids=(), user_ids=()):
    # Converter lead em cliente dispara o kit de admissão (procuração +
    # contrato em legal_docs); sem apagar essas dependências, o DELETE de
    # clients viola FK e o cliente sobrevive para contaminar outros testes.
    await limpar_dependencias_de_clientes(db, client_ids)
    for cid in client_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE registro_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_criar_lead_aparece_no_funil_com_etapa():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import criar, listar

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        await db.commit()
        cu = await _carregar_user(db, uid)
        cid = None
        try:
            # Payload idêntico ao do board (CRMLeads.tsx save()).
            payload = ClientCreate(
                nome="Lead Fictício do Funil",
                telefone="(31) 99999-0000",
                area_interesse="Trabalhista",
                origem_lead="Indicação",
                observacoes="teste automatizado",
                status="lead",
                etapa_funil="lead",
            )
            c = await criar(payload, db=db, cu=cu)
            cid = c.id
            status_val = getattr(c.status, "value", c.status)
            assert status_val == "lead"          # NÃO vira "ativo"
            assert c.etapa_funil == "lead"
            assert c.origem_lead == "Indicação"
            assert c.area_interesse == "Trabalhista"

            # Board: GET /clients/?status=lead devolve o lead com etapa preenchida.
            r = await listar(page=1, page_size=500, search=None, status_f="lead", db=db, cu=cu)
            achado = next((x for x in r["data"] if x.id == cid), None)
            assert achado is not None, "lead criado não apareceu no funil"
            assert achado.etapa_funil == "lead"

            # E NÃO aparece entre os ativos.
            r_ativos = await listar(page=1, page_size=500, search=None,
                                    status_f="ativo", db=db, cu=cu)
            assert all(x.id != cid for x in r_ativos["data"])
        finally:
            await _limpar(db, client_ids=[cid] if cid else (), user_ids=[uid])


async def test_criar_lead_sem_etapa_recebe_default_lead():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import criar

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        await db.commit()
        cu = await _carregar_user(db, uid)
        cid = None
        try:
            c = await criar(ClientCreate(nome="Lead Sem Etapa", status="lead"), db=db, cu=cu)
            cid = c.id
            assert c.etapa_funil == "lead"
        finally:
            await _limpar(db, client_ids=[cid] if cid else (), user_ids=[uid])


async def test_mover_etapa_e_converter_lead():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import atualizar, criar, listar

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        await db.commit()
        cu = await _carregar_user(db, uid)
        cid = None
        try:
            c = await criar(ClientCreate(nome="Lead Arrastável", status="lead",
                                         etapa_funil="lead"), db=db, cu=cu)
            cid = c.id

            # Drag do board: PATCH {etapa_funil: "proposta"}.
            c = await atualizar(cid, ClientUpdate(etapa_funil="proposta"), db=db, cu=cu)
            assert c.etapa_funil == "proposta"

            # Conversão: PATCH {etapa_funil: "convertido", status: "ativo"}.
            c = await atualizar(cid, ClientUpdate(etapa_funil="convertido",
                                                  status="ativo"), db=db, cu=cu)
            assert getattr(c.status, "value", c.status) == "ativo"

            r = await listar(page=1, page_size=500, search=None, status_f="lead", db=db, cu=cu)
            assert all(x.id != cid for x in r["data"])  # saiu do funil
        finally:
            await _limpar(db, client_ids=[cid] if cid else (), user_ids=[uid])


async def test_cliente_comum_continua_ativo_por_default():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import criar

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        await db.commit()
        cu = await _carregar_user(db, uid)
        cid = None
        try:
            c = await criar(ClientCreate(nome="Cliente Comum Fictício"), db=db, cu=cu)
            cid = c.id
            assert getattr(c.status, "value", c.status) == "ativo"
            assert c.etapa_funil is None
        finally:
            await _limpar(db, client_ids=[cid] if cid else (), user_ids=[uid])


def test_status_e_etapa_invalidos_rejeitados():
    with pytest.raises(ValidationError):
        ClientCreate(nome="X", status="vip")
    with pytest.raises(ValidationError):
        ClientCreate(nome="X", status="lead", etapa_funil="negociando")
    with pytest.raises(ValidationError):
        ClientUpdate(etapa_funil="qualquer")
    with pytest.raises(ValidationError):
        ClientUpdate(status="vip")
