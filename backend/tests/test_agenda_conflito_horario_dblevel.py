"""Agenda: detecção de conflito de horário (double-booking) + lembrete de
audiências da agenda no scheduler.

Contrato coberto:
  - `_buscar_conflitos` (agenda_eventos): eventos NÃO concluídos do MESMO
    responsável na MESMA data e MESMA hora (início exato). Evento sem hora não
    colide — e o short-circuit NEM toca o banco (testes DB-free abaixo).
  - POST /agenda-eventos (criar): AVISA, não bloqueia — cria o evento e devolve
    `conflito_agenda` no corpo com as colisões (lista vazia quando não há).
  - PATCH /agenda-eventos/{id} (atualizar): mesma política; exclui a si mesmo;
    evento que virou concluído não conflita.
  - `_alertar_audiencias_agenda` (scheduler): audiência (tipo='audiencia') não
    concluída a exatamente 3/1/0 dias gera UMA notificação 'audiencia' ao
    responsável. Idempotente: 2ª execução no mesmo dia não re-alerta (dedup via
    modelo Notification, janela ~20h). Fora do limiar (ex.: 2 dias) e concluída
    NÃO alertam.

Os testes de integração usam Postgres (padrão dos demais *_dblevel.py: handler/
router direto com `AsyncSessionLocal`). Sem RUN_DB_TESTS=1, pulam. Os testes de
short-circuit do `_buscar_conflitos` rodam SEMPRE (não tocam o banco).
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.routers.agenda_eventos import (
    _buscar_conflitos, criar, atualizar, EventoIn, EventoPatch,
)


# ── DB-free: short-circuit não deve tocar o banco ────────────────────────────

class _DbProibido:
    """db cujo execute FALHA — prova que `_buscar_conflitos` retornou antes de
    consultar o banco (short-circuit)."""
    async def execute(self, *a, **k):  # pragma: no cover - só falha se chamado
        raise AssertionError("execute não deveria ser chamado no short-circuit")


async def test_conflito_sem_hora_nao_toca_banco():
    out = await _buscar_conflitos(
        _DbProibido(), responsavel_id="u1", data_evento=date.today(), hora=None,
    )
    assert out == []


async def test_conflito_hora_vazia_ou_espacos_nao_toca_banco():
    for h in ("", "   "):
        out = await _buscar_conflitos(
            _DbProibido(), responsavel_id="u1", data_evento=date.today(), hora=h,
        )
        assert out == []


async def test_conflito_sem_responsavel_nao_toca_banco():
    out = await _buscar_conflitos(
        _DbProibido(), responsavel_id=None, data_evento=date.today(), hora="14:00",
    )
    assert out == []


# ── Integração (Postgres) ────────────────────────────────────────────────────

_pg = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Agenda Teste', :role, true)"),
        {"id": uid, "email": f"ag-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _carregar_user(db, uid: str):
    from app.models.user import User
    from sqlalchemy import select
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _inserir_evento(db, *, resp, data_evento, hora, tipo="audiencia",
                          concluido=False, titulo=None) -> str:
    eid = str(uuid4())
    await db.execute(
        text("INSERT INTO agenda_eventos (id, titulo, tipo, data_evento, hora, "
             "responsavel_id, concluido, created_by) VALUES "
             "(:id, :t, :tp, :d, :h, :resp, :c, :resp)"),
        {"id": eid, "t": titulo or f"Evt {eid[:8]}", "tp": tipo, "d": data_evento,
         "h": hora, "resp": resp, "c": concluido},
    )
    return eid


async def _contar_notif(db, user_id: str, tipo: str = "audiencia") -> int:
    return (await db.execute(
        text("SELECT count(*) FROM notifications WHERE user_id = :u AND tipo = :t"),
        {"u": user_id, "t": tipo},
    )).scalar()


async def _limpar(db, *, user_ids=()):
    for uid in user_ids:
        await db.execute(text("DELETE FROM agenda_eventos WHERE responsavel_id = :id OR created_by = :id"), {"id": uid})
        await db.execute(text("DELETE FROM notifications WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


@_pg
async def test_criar_avisa_conflito_mesma_data_hora_sem_bloquear():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db)
        await db.commit()
        try:
            cu = await _carregar_user(db, adv)
            d = date.today() + timedelta(days=10)
            out1 = await criar(
                EventoIn(titulo="Audiência A", tipo="audiencia",
                         data_evento=d, hora="14:00"), db=db, cu=cu)
            assert out1["conflito_agenda"] == []          # primeiro: sem colisão
            # segundo evento MESMO responsável/data/hora → cria mas AVISA.
            out2 = await criar(
                EventoIn(titulo="Reunião B", tipo="reuniao",
                         data_evento=d, hora="14:00"), db=db, cu=cu)
            assert "id" in out2 and out2["ok"] is True     # NÃO bloqueou
            assert len(out2["conflito_agenda"]) == 1
            assert out2["conflito_agenda"][0]["titulo"] == "Audiência A"
            # hora diferente → sem conflito.
            out3 = await criar(
                EventoIn(titulo="C", data_evento=d, hora="16:00"), db=db, cu=cu)
            assert out3["conflito_agenda"] == []
            # sem hora → nunca colide por horário.
            out4 = await criar(
                EventoIn(titulo="D", data_evento=d, hora=None), db=db, cu=cu)
            assert out4["conflito_agenda"] == []
        finally:
            await _limpar(db, user_ids=[adv])


@_pg
async def test_atualizar_detecta_conflito_e_ignora_concluido():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db)
        d = date.today() + timedelta(days=12)
        a = await _inserir_evento(db, resp=adv, data_evento=d, hora="09:00", titulo="A")
        b = await _inserir_evento(db, resp=adv, data_evento=d, hora="10:00", titulo="B")
        await db.commit()
        try:
            cu = await _carregar_user(db, adv)
            # move B para 09:00 → conflita com A (exclui a si mesmo).
            out = await atualizar(b, EventoPatch(hora="09:00"), db=db, cu=cu)
            assert len(out["conflito_agenda"]) == 1
            assert out["conflito_agenda"][0]["titulo"] == "A"
            # concluir A: B (que segue em 09:00) não deve mais colidir com A.
            out2 = await atualizar(b, EventoPatch(concluido=True), db=db, cu=cu)
            assert out2["conflito_agenda"] == []           # B concluído não checa
            out3 = await atualizar(a, EventoPatch(titulo="A editado"), db=db, cu=cu)
            assert out3["conflito_agenda"] == []           # B concluído não colide
        finally:
            await _limpar(db, user_ids=[adv])


@_pg
async def test_scheduler_alerta_audiencia_3d_uma_vez_e_ignora_2d_e_concluida():
    from app.core.database import AsyncSessionLocal
    from app.services.scheduler import _alertar_audiencias_agenda
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db)
        d3 = date.today() + timedelta(days=3)
        d2 = date.today() + timedelta(days=2)
        await _inserir_evento(db, resp=adv, data_evento=d3, hora="14:00", titulo="Aud 3d")
        await _inserir_evento(db, resp=adv, data_evento=d2, hora="14:00", titulo="Aud 2d")
        await _inserir_evento(db, resp=adv, data_evento=d3, hora="15:00",
                              titulo="Aud concluida", concluido=True)
        await db.commit()
        try:
            await _alertar_audiencias_agenda()
            async with AsyncSessionLocal() as db2:
                # só a de 3 dias, não concluída, alerta.
                assert await _contar_notif(db2, adv) == 1
            # 2ª execução no mesmo dia: dedup por Notification → não re-alerta.
            await _alertar_audiencias_agenda()
            async with AsyncSessionLocal() as db3:
                assert await _contar_notif(db3, adv) == 1
        finally:
            await _limpar(db, user_ids=[adv])
