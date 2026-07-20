"""Timeline e saúde operacional com Postgres real."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _fixtures(db) -> tuple[str, str]:
    client_id = str(uuid4())
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO clients (id, tipo, nome, email, status) "
            "VALUES (:id, 'PF', 'Cliente Timeline', :email, 'ativo')"
        ),
        {"id": client_id, "email": f"timeline-{client_id[:8]}@teste.local"},
    )
    await db.execute(
        text(
            "INSERT INTO cases "
            "(id, titulo, area, status, client_id, has_judicial_process, "
            " created_at, updated_at) "
            "VALUES (:id, 'Caso Timeline', 'civil', 'ativo', :client_id, true, "
            " now() - interval '60 days', now() - interval '60 days')"
        ),
        {"id": case_id, "client_id": client_id},
    )
    await db.commit()
    return client_id, case_id


async def _cleanup(db, client_id: str, case_id: str) -> None:
    for table in (
        "case_movimentos",
        "legal_docs",
        "deadlines",
        "tasks",
        "atendimentos",
        "documents",
        "processes",
    ):
        await db.execute(text(f"DELETE FROM {table} WHERE case_id=:id"), {"id": case_id})
    await db.execute(text("DELETE FROM cases WHERE id=:id"), {"id": case_id})
    await db.execute(text("DELETE FROM clients WHERE id=:id"), {"id": client_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def test_timeline_orders_sources_and_reports_real_truncation():
    from app.core.database import AsyncSessionLocal
    from app.services.case_timeline_service import timeline

    async with AsyncSessionLocal() as db:
        client_id, case_id = await _fixtures(db)
        try:
            for idx in range(2):
                await db.execute(
                    text(
                        "INSERT INTO documents "
                        "(id, titulo, filename, filepath, confidencialidade, case_id, "
                        " created_at, updated_at) "
                        "VALUES (:id, :titulo, :filename, :filepath, 'normal', :case_id, "
                        " now() - interval '2 days', now() - interval '2 days')"
                    ),
                    {
                        "id": str(uuid4()),
                        "titulo": f"Documento {idx}",
                        "filename": f"arquivo-{idx}.pdf",
                        "filepath": f"/tmp/arquivo-{idx}.pdf",
                        "case_id": case_id,
                    },
                )
            await db.execute(
                text(
                    "INSERT INTO case_movimentos "
                    "(id, case_id, tipo, descricao, data_evento, created_at) "
                    "VALUES (:id, :case_id, 'nota', 'Movimento recente', now(), now())"
                ),
                {"id": str(uuid4()), "case_id": case_id},
            )
            await db.commit()

            result = await timeline(
                db,
                case_id,
                page=1,
                per_page=20,
                source_limit=1,
            )
            assert result["items"][0]["source"] == "case_movimentos"
            assert result["truncated"] is True
            assert "documents" in result["saturated_sources"]
            assert result["has_more"] is True
            document = next(
                item for item in result["items"] if item["source"] == "documents"
            )
            assert document["description"].startswith("arquivo-")
        finally:
            await _cleanup(db, client_id, case_id)


async def test_health_detects_deadline_inactivity_missing_process_and_next_action():
    from app.core.database import AsyncSessionLocal
    from app.services.case_health_service import operational_health

    async with AsyncSessionLocal() as db:
        client_id, case_id = await _fixtures(db)
        try:
            await db.execute(
                text(
                    "INSERT INTO deadlines "
                    "(id, titulo, tipo, prioridade, status, data_prazo, case_id, "
                    " confirmado, origem, created_at, updated_at) "
                    "VALUES (:id, 'Prazo vencido', 'processual', 'critica', 'pendente', "
                    " CURRENT_DATE - 1, :case_id, true, 'manual', "
                    " now() - interval '40 days', now() - interval '40 days')"
                ),
                {"id": str(uuid4()), "case_id": case_id},
            )
            await db.commit()

            result = await operational_health(db, case_id, stale_days=30)
            codes = [item["code"] for item in result["indicators"]]
            assert result["found"] is True
            assert result["metrics"]["overdue_deadlines"] == 1
            assert result["metrics"]["active_processes"] == 0
            assert result["metrics"]["actionable_tasks"] == 0
            assert codes[0] == "OVERDUE_DEADLINES"
            assert "CASE_INACTIVE" in codes
            assert "NO_ACTIONABLE_TASK" in codes
            assert "MISSING_ACTIVE_PROCESS" in codes
            assert result["score"] < 65
            assert result["next_recommended_action"] == result["indicators"][0][
                "recommended_action"
            ]
        finally:
            await _cleanup(db, client_id, case_id)
