# -*- coding: utf-8 -*-
"""Persistência do Diagnóstico 360 (migration 141) — testes dblevel.

Cobertura cirúrgica do caminho habilitado pelo PR #1108:
- readiness com persistir=True cria run em rascunho com HITL (requer_revisao);
- readiness com persistir=False (sondagem/GET) não gera run;
- empresa inexistente devolve None sem gerar run;
- o contador `diagnosticos_pendentes` do dashboard respeita o escopo de
  visibilidade e exclui runs descartados (não infla o contador).

RUN_DB_TESTS=1 exigido (grava em dpt_diagnosticos).
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text as sql

pytestmark = [
    pytest.mark.skipif(
        not __import__("os").environ.get("RUN_DB_TESTS"),
        reason="exige banco de dados (RUN_DB_TESTS=1)",
    )
]


@pytest.fixture
def _client_e_user_db():
    from app.core.database import AsyncSessionLocal
    from app.models.client import Client, ClientTipo
    from app.models.user import User

    async def _seed():
        async with AsyncSessionLocal() as db:
            await db.execute(
                sql(
                    "DELETE FROM dpt_diagnosticos WHERE client_id IN "
                    "(SELECT id FROM clients WHERE razao_social LIKE 'dpt360-pers-%')"
                )
            )
            await db.execute(
                sql("DELETE FROM clients WHERE razao_social LIKE 'dpt360-pers-%'")
            )
            from app.models.user import UserRole

            user = User(
                id=uuid.uuid4().hex,
                full_name="DPT360 Persistência",
                email=f"dpt360-pers-{uuid.uuid4().hex[:8]}@ejc.local",
                hashed_password="x",
                role=UserRole.admin,
            )
            db.add(user)
            await db.flush()
            client = Client(
                id=uuid.uuid4().hex,
                razao_social=f"dpt360-pers-{uuid.uuid4().hex[:8]}",
                tipo=ClientTipo.PJ,
                responsavel_id=user.id,
            )
            db.add(client)
            await db.commit()
            await db.refresh(user)
            await db.refresh(client)
            return user, client

    async def _limpar(client_id: str):
        async with AsyncSessionLocal() as db:
            await db.execute(
                sql("DELETE FROM dpt_diagnosticos WHERE client_id = :c"),
                {"c": client_id},
            )
            await db.execute(
                sql("DELETE FROM clients WHERE id = :c"), {"c": client_id}
            )
            await db.commit()

    user, client = asyncio.run(_seed())
    yield user, client
    asyncio.run(_limpar(client.id))


@pytest.mark.asyncio
async def test_readiness_persistir_cria_run_rascunho_hitl(_client_e_user_db):
    from app.core.database import AsyncSessionLocal
    from app.models.dpt_diagnostico import DptDiagnosticEstado, DptDiagnosticRun
    from app.modules.dpt360.diagnostic_service import build_diagnostic_readiness

    user, client = _client_e_user_db
    async with AsyncSessionLocal() as db:
        result = await build_diagnostic_readiness(
            db, user, client.id, "completo", persistir=True
        )
        # O service grava o run na sessão, mas o commit é responsabilidade do
        # chamador (o router faz commit quando persistir=True) — reproduzir o
        # mesmo contrato aqui.
        await db.commit()
        run = (
            await db.execute(
                select(DptDiagnosticRun).where(
                    DptDiagnosticRun.client_id == client.id
                )
            )
        ).scalar_one()
        assert run.estado == DptDiagnosticEstado.rascunho.value
    assert result is not None
    assert result.persistencia == "habilitada"
    async with AsyncSessionLocal() as db:
        run = (
            await db.execute(
                select(DptDiagnosticRun).where(
                    DptDiagnosticRun.client_id == client.id
                )
            )
        ).scalar_one()
        assert run.estado == DptDiagnosticEstado.rascunho.value
        assert run.requer_revisao is True
        assert run.tipo == "completo"
        assert run.areas_json  # evidências por área serializadas
        assert run.created_by == user.id


@pytest.mark.asyncio
async def test_readiness_probe_nao_gera_run(_client_e_user_db):
    from app.core.database import AsyncSessionLocal
    from app.models.dpt_diagnostico import DptDiagnosticRun
    from app.modules.dpt360.diagnostic_service import build_diagnostic_readiness

    user, client = _client_e_user_db
    async with AsyncSessionLocal() as db:
        result = await build_diagnostic_readiness(
            db, user, client.id, "completo", persistir=False
        )
    assert result is not None
    async with AsyncSessionLocal() as db:
        runs = (
            await db.execute(
                select(DptDiagnosticRun).where(
                    DptDiagnosticRun.client_id == client.id
                )
            )
        ).scalars().all()
    assert runs == []


@pytest.mark.asyncio
async def test_readiness_empresa_inexistente_nao_gera_run():
    from app.core.database import AsyncSessionLocal
    from app.models.dpt_diagnostico import DptDiagnosticRun
    from app.models.user import User
    from app.modules.dpt360.diagnostic_service import build_diagnostic_readiness

    async with AsyncSessionLocal() as db:
        usuario = (await db.execute(select(User).limit(1))).scalar_one()
        result = await build_diagnostic_readiness(
            db, usuario, "cliente-inexistente-xxx", "completo", persistir=True
        )
    assert result is None
    async with AsyncSessionLocal() as db:
        runs = (
            await db.execute(
                select(DptDiagnosticRun).where(
                    DptDiagnosticRun.client_id == "cliente-inexistente-xxx"
                )
            )
        ).scalars().all()
    assert runs == []


@pytest.mark.asyncio
async def test_dashboard_pendentes_exclui_descartado_e_respeita_escopo(
    _client_e_user_db,
):
    from app.core.database import AsyncSessionLocal
    from app.models.dpt_diagnostico import DptDiagnosticEstado
    from app.modules.dpt360.dashboard_service import build_dashboard

    user, client = _client_e_user_db
    # insere manualmente um run descartado (requer_revisao=True por default) e
    # um run rascunho, para validar o filtro do contador
    async with AsyncSessionLocal() as db:
        await db.execute(
            sql(
                "INSERT INTO dpt_diagnosticos "
                "(id, client_id, tipo, areas_json, estado, requer_revisao, created_by, created_at) "
                "VALUES (:i, :c, 'tributario', '{}', :e, true, :u, now())"
            ),
            {
                "i": uuid.uuid4().hex,
                "c": client.id,
                "e": DptDiagnosticEstado.descartado.value,
                "u": user.id,
            },
        )
        await db.execute(
            sql(
                "INSERT INTO dpt_diagnosticos "
                "(id, client_id, tipo, areas_json, estado, requer_revisao, created_by, created_at) "
                "VALUES (:i, :c, 'completo', '{}', :e, true, :u, now())"
            ),
            {
                "i": uuid.uuid4().hex,
                "c": client.id,
                "e": DptDiagnosticEstado.rascunho.value,
                "u": user.id,
            },
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        dash = await build_dashboard(db, user)
    # só o rascunho conta; o descartado não infla o contador
    assert dash.metrics.diagnosticos_pendentes == 1
