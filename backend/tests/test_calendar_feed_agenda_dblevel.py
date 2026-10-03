"""Feed ICS em banco real: `agenda_eventos` entram no calendário (achado A4).

Chama o handler direto (padrão *_dblevel.py). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.routers import calendar_feed

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db) -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Feed Agenda Teste', 'advogado', true)"),
        {"id": uid, "email": f"ics-{uid[:8]}@teste.local"},
    )
    return uid


async def _evento(db, *, resp, titulo, data_evento, tipo="audiencia", hora=None,
                  concluido=False, deleted=False) -> str:
    eid = str(uuid4())
    await db.execute(
        text("INSERT INTO agenda_eventos (id, titulo, tipo, data_evento, hora, "
             "responsavel_id, created_by, concluido, deleted_at) VALUES "
             "(:id, :t, :tipo, :d, :h, :resp, :resp, :c, "
             " CASE WHEN :del THEN now() ELSE NULL END)"),
        {"id": eid, "t": titulo, "tipo": tipo, "d": data_evento, "h": hora,
         "resp": resp, "c": concluido, "del": deleted},
    )
    return eid


@pytest.mark.asyncio
async def test_feed_inclui_eventos_da_agenda_do_responsavel():
    hoje = date.today()
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db)
        outro = await _criar_user(db)
        visivel = await _evento(db, resp=dono, titulo="Audiência UNA",
                                data_evento=hoje + timedelta(days=5), hora="10:00")
        concluido = await _evento(db, resp=dono, titulo="Já feita",
                                  data_evento=hoje + timedelta(days=2), concluido=True)
        excluido = await _evento(db, resp=dono, titulo="Excluída",
                                 data_evento=hoje + timedelta(days=2), deleted=True)
        passado = await _evento(db, resp=dono, titulo="Passada",
                                data_evento=hoje - timedelta(days=1))
        alheio = await _evento(db, resp=outro, titulo="De outro advogado",
                               data_evento=hoje + timedelta(days=3))
        await db.commit()

    token = calendar_feed.gerar_token_calendario(dono, 1)
    resposta = await calendar_feed.feed_ics(dono, token)
    corpo = resposta.body.decode()

    assert f"UID:ejc-agenda-{visivel}@" in corpo
    assert "BEGIN:VTIMEZONE" in corpo
    for ausente in (concluido, excluido, passado, alheio):
        assert ausente not in corpo
