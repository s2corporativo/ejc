"""Regras canônicas de Processo com Postgres real.

Cobre os pontos em que a separação Caso × Processo pode corromper o espelho
legado ou violar a unicidade sem gerar erro evidente no router.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _fixture_case(db) -> tuple[str, str]:
    client_id = str(uuid4())
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO clients (id, tipo, nome, email, status) "
            "VALUES (:id, 'PF', 'Cliente Processo', :email, 'ativo')"
        ),
        {"id": client_id, "email": f"process-{client_id[:8]}@teste.local"},
    )
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id) "
            "VALUES (:id, 'Caso Processo', 'civil', 'ativo', :client_id)"
        ),
        {"id": case_id, "client_id": client_id},
    )
    await db.commit()
    return client_id, case_id


async def _cleanup(db, client_id: str, case_id: str) -> None:
    await db.execute(text("DELETE FROM processes WHERE case_id = :id"), {"id": case_id})
    await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": case_id})
    await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def test_write_through_preserva_dado_canonico_e_respeita_largura_legada():
    from app.core.database import AsyncSessionLocal
    from app.models.case import Case
    from app.models.process import Process
    from app.schemas.process import ProcessCreate
    from app.services import processo_service

    async with AsyncSessionLocal() as db:
        client_id, case_id = await _fixture_case(db)
        tribunal = "TRIBUNAL-CANONICO-COM-NOME-MUITO-MAIOR-QUE-VINTE"
        comarca = "C" * 130
        vara = "V" * 130
        try:
            created = await processo_service.criar_processo(
                case_id,
                ProcessCreate(
                    numero_cnj="PROC-LEGADO-2026",
                    tribunal=tribunal,
                    comarca=comarca,
                    vara=vara,
                    tipo="judicial",
                ),
                db,
            )
            await db.commit()

            process = (
                await db.execute(select(Process).where(Process.id == created["id"]))
            ).scalar_one()
            case = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one()

            assert process.tribunal == tribunal
            assert process.comarca == comarca
            assert process.vara == vara
            assert case.tribunal == tribunal[:20]
            assert case.comarca == comarca[:100]
            assert case.vara == vara[:100]
            assert case.numero_processo == "PROC-LEGADO-2026"
            assert case.has_judicial_process is True
        finally:
            await _cleanup(db, client_id, case_id)


async def test_arquivar_ultimo_principal_limpa_espelho_do_caso():
    from app.core.database import AsyncSessionLocal
    from app.models.case import Case
    from app.schemas.process import ProcessCreate
    from app.services import processo_service

    async with AsyncSessionLocal() as db:
        client_id, case_id = await _fixture_case(db)
        try:
            created = await processo_service.criar_processo(
                case_id,
                ProcessCreate(numero_cnj="PROC-UNICO", tribunal="TJMG"),
                db,
            )
            await processo_service.arquivar_processo(created["id"], "encerrado", db)
            await db.commit()

            case = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one()
            assert case.numero_processo is None
            assert case.tribunal is None
            assert case.comarca is None
            assert case.vara is None
            assert case.valor_causa is None
            assert case.has_judicial_process is False
        finally:
            await _cleanup(db, client_id, case_id)


async def test_principal_so_vira_acessorio_com_demovacao_explicita():
    from app.core.database import AsyncSessionLocal
    from app.models.process import Process
    from app.schemas.process import ProcessCreate, ProcessUpdate
    from app.services import processo_service

    async with AsyncSessionLocal() as db:
        client_id, case_id = await _fixture_case(db)
        try:
            principal = await processo_service.criar_processo(
                case_id,
                ProcessCreate(numero_cnj="PROC-PRINCIPAL"),
                db,
            )
            acessorio = await processo_service.criar_processo(
                case_id,
                ProcessCreate(
                    numero_cnj="PROC-ACESSORIO",
                    tipo="recurso",
                    processo_principal_id=principal["id"],
                ),
                db,
            )

            with pytest.raises(processo_service.ProcessConflict):
                await processo_service.atualizar_processo(
                    principal["id"],
                    ProcessUpdate(processo_principal_id=acessorio["id"]),
                    db,
                )

            changed = await processo_service.atualizar_processo(
                principal["id"],
                ProcessUpdate(
                    processo_principal_id=acessorio["id"],
                    is_principal=False,
                ),
                db,
            )
            await db.commit()

            rows = (
                await db.execute(
                    select(Process).where(Process.case_id == case_id).order_by(Process.id)
                )
            ).scalars().all()
            by_id = {row.id: row for row in rows}
            assert changed["is_principal"] is False
            assert by_id[principal["id"]].processo_principal_id == acessorio["id"]
            assert by_id[acessorio["id"]].is_principal is True
            assert by_id[acessorio["id"]].processo_principal_id is None
        finally:
            await _cleanup(db, client_id, case_id)


async def test_criacao_arquivada_registra_timestamp_sem_virar_principal():
    from app.core.database import AsyncSessionLocal
    from app.models.process import Process
    from app.schemas.process import ProcessCreate
    from app.services import processo_service

    async with AsyncSessionLocal() as db:
        client_id, case_id = await _fixture_case(db)
        try:
            created = await processo_service.criar_processo(
                case_id,
                ProcessCreate(numero_cnj="PROC-ARQUIVADO", status="arquivado"),
                db,
            )
            await db.commit()
            process = (
                await db.execute(select(Process).where(Process.id == created["id"]))
            ).scalar_one()
            assert process.status == "arquivado"
            assert process.archived_at is not None
            assert process.is_principal is False
        finally:
            await _cleanup(db, client_id, case_id)
