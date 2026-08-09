"""Kanban é organização visual e não pode substituir transições de Case.

O endpoint deve bloquear entrada em status terminal e também impedir que um caso
já encerrado/arquivado seja visualmente movido para coluna ativa antes da
reabertura canônica. A decisão é serializada com `FOR UPDATE` para não usar
estado obsoleto diante de transição concorrente.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "estagiario") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Kanban Teste', :role, true)"),
        {"id": uid, "email": f"kanban-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db, nome: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(
    db, client_id: str, titulo: str, *, resp_id: str, auxiliar_id: str | None = None,
    status: str = "em_instrucao",
) -> str:
    assert status in ("em_instrucao", "encerrado", "arquivado", "aberto")
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id, "
            "advogado_responsavel_id, advogado_auxiliar_id, proxima_acao, kanban_column) "
            f"VALUES (:id, :titulo, 'civil', '{status}', :cid, :resp, :aux, "
            "'Providenciar X', 'Em andamento')"
        ),
        {"id": case_id, "titulo": titulo, "cid": client_id, "resp": resp_id, "aux": auxiliar_id},
    )
    return case_id


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_estagiario_nao_arquiva_nem_encerra_arrastando_cartao():
    from app.core.database import AsyncSessionLocal
    from app.routers.kanban import update_case_kanban

    tok = f"Kan{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        estagiario = await _criar_user(db, "estagiario")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=socio, auxiliar_id=estagiario)
        await db.commit()
        try:
            cu = await _carregar_user(db, estagiario)
            for coluna, termo in (("Arquivado", "arquivar"), ("Encerrado", "encerrar")):
                with pytest.raises(HTTPException) as exc:
                    await update_case_kanban(
                        caso, {"kanban_column": coluna, "kanban_position": 0}, db, cu,
                    )
                assert exc.value.status_code == 422
                assert termo in str(exc.value.detail).lower()

            status_atual = (await db.execute(
                text("SELECT status FROM cases WHERE id = :id"), {"id": caso},
            )).scalar()
            assert status_atual == "em_instrucao"
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[socio, estagiario], client_ids=[cli])


async def test_kanban_move_livre_para_coluna_nao_terminal_sem_mudar_status():
    from app.core.database import AsyncSessionLocal
    from app.routers.kanban import update_case_kanban

    tok = f"Kan{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        estagiario = await _criar_user(db, "estagiario")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=estagiario)
        await db.commit()
        try:
            cu = await _carregar_user(db, estagiario)
            resultado = await update_case_kanban(
                caso, {"kanban_column": "Em elaboração", "kanban_position": 2}, db, cu,
            )
            assert resultado["status_sincronizado"] is None
            row = (await db.execute(
                text("SELECT status, kanban_column, kanban_position FROM cases WHERE id=:id"),
                {"id": caso},
            )).one()
            assert row[0] == "em_instrucao"
            assert row[1] == "Em elaboração"
            assert row[2] == 2
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[estagiario], client_ids=[cli])


@pytest.mark.parametrize("status", ["encerrado", "arquivado"])
async def test_kanban_nao_reabre_caso_terminal_por_coluna_ativa(status: str):
    from app.core.database import AsyncSessionLocal
    from app.routers.kanban import update_case_kanban

    tok = f"Reab{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=socio, status=status)
        await db.execute(
            text(
                "UPDATE cases SET archived_at=:agora, archive_reason='Registro terminal', "
                "data_encerramento=:agora, resultado='exito_total' WHERE id=:id"
            ),
            {"id": caso, "agora": datetime.now(timezone.utc)},
        )
        await db.commit()
        try:
            cu = await _carregar_user(db, socio)
            with pytest.raises(HTTPException) as exc:
                await update_case_kanban(
                    caso,
                    {"kanban_column": "Aguardando prazo", "kanban_position": 0},
                    db,
                    cu,
                )
            assert exc.value.status_code == 422
            assert "reabra" in str(exc.value.detail).lower()

            row = (await db.execute(
                text(
                    "SELECT status, archived_at, archive_reason, data_encerramento, resultado "
                    "FROM cases WHERE id=:id"
                ),
                {"id": caso},
            )).one()
            assert row[0] == status
            assert row[1] is not None
            assert row[2] == "Registro terminal"
            assert row[3] is not None
            assert row[4] == "exito_total"
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[socio], client_ids=[cli])


async def test_kanban_rele_status_apos_lock_concorrente_e_bloqueia_reabertura():
    """Se outra transação arquivar enquanto o Kanban aguarda, o handler deve
    reler o status depois do lock e recusar a movimentação para coluna ativa."""
    from app.core.database import AsyncSessionLocal
    from app.routers.kanban import update_case_kanban

    tok = f"Conc{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as setup:
        socio = await _criar_user(setup, "socio")
        cli = await _criar_cliente(setup, f"Cliente {tok}")
        caso = await _criar_caso(setup, cli, f"Caso {tok}", resp_id=socio, status="aberto")
        await setup.commit()

    try:
        async with AsyncSessionLocal() as escritor, AsyncSessionLocal() as kanban_db:
            cu = await _carregar_user(kanban_db, socio)
            await escritor.execute(text("SELECT id FROM cases WHERE id=:id FOR UPDATE"), {"id": caso})
            await escritor.execute(
                text(
                    "UPDATE cases SET status='arquivado', archived_at=:agora, "
                    "archive_reason='Concorrente' WHERE id=:id"
                ),
                {"id": caso, "agora": datetime.now(timezone.utc)},
            )

            tarefa = asyncio.create_task(
                update_case_kanban(
                    caso,
                    {"kanban_column": "Aguardando prazo", "kanban_position": 0},
                    kanban_db,
                    cu,
                )
            )
            await asyncio.sleep(0.1)
            assert not tarefa.done(), "Kanban não aguardou o lock concorrente"
            await escritor.commit()

            with pytest.raises(HTTPException) as exc:
                await asyncio.wait_for(tarefa, timeout=5)
            assert exc.value.status_code == 422
            assert "reabra" in str(exc.value.detail).lower()

            row = (await kanban_db.execute(
                text("SELECT status, archived_at, archive_reason FROM cases WHERE id=:id"),
                {"id": caso},
            )).one()
            assert row[0] == "arquivado"
            assert row[1] is not None
            assert row[2] == "Concorrente"
    finally:
        async with AsyncSessionLocal() as cleanup:
            await _limpar(cleanup, case_ids=[caso], user_ids=[socio], client_ids=[cli])
