"""Agenda de eventos — gates de visibilidade e de responsável (re-auditoria).

Contrato coberto (espelha o gate de escrita M-S2 do PATCH/DELETE):
  - N1+M1 GET /agenda-eventos/: evento SEM caso é PESSOAL e só aparece para
    criador, responsável ou gestão; evento COM caso segue o padrão EXISTS de
    atividades.py — só responsável do evento, advogado responsável/auxiliar do
    caso ou gestão. Advogado alheio NÃO enxerga nem o pessoal nem o de caso
    alheio (antes todo evento com case_id vazava p/ qualquer interno).
  - N2a POST /agenda-eventos/: criar evento com responsavel_id de OUTRO usuário
    exige gestão (403 p/ advogado); responsavel_id próprio/ausente continua
    livre; gestão cria para qualquer um.
  - N2a PATCH: transferir para terceiro exige gestão; manter o responsável
    atual (no-op) não bloqueia.
  - N2b conflito_agenda: quando o responsável dos eventos colidentes não é o
    chamador (e ele não é gestão), titulo/local são censurados — só a
    existência e o horário são revelados. Gestão segue vendo tudo.

Postgres é OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: chama o handler
direto com AsyncSessionLocal). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.routers.agenda_eventos import (
    listar, criar, atualizar, remover, EventoIn, EventoPatch,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


# ── Helpers (SQL cru, como nos demais *_dblevel.py) ─────────────────────────────

async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Agenda Gate Teste', :role, true)"),
        {"id": uid, "email": f"agg-{uid[:8]}@teste.local", "role": role},
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


async def _criar_caso(db, client_id: str, titulo: str, resp_id: str | None = None) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "advogado_responsavel_id) VALUES "
             "(:id, :titulo, 'civil', 'em_instrucao', :cid, :resp)"),
        {"id": case_id, "titulo": titulo, "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _inserir_evento(db, *, resp, created_by=None, data_evento, hora=None,
                          case_id=None, titulo="Evento", local=None) -> str:
    eid = str(uuid4())
    await db.execute(
        text("INSERT INTO agenda_eventos (id, titulo, tipo, data_evento, hora, "
             "local, case_id, responsavel_id, created_by) VALUES "
             "(:id, :t, 'compromisso', :d, :h, :l, :cid, :resp, :cb)"),
        {"id": eid, "t": titulo, "d": data_evento, "h": hora, "l": local,
         "cid": case_id, "resp": resp, "cb": created_by or resp},
    )
    return eid


async def _carregar_user(db, uid: str):
    from sqlalchemy import select
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, user_ids=(), case_ids=(), client_ids=()):
    for uid in user_ids:
        await db.execute(text(
            "DELETE FROM agenda_eventos WHERE responsavel_id = :id OR created_by = :id"
        ), {"id": uid})
    for cid in case_ids:
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


def _ids(out) -> set[str]:
    return {r["id"] for r in out["data"]}


# ── N1+M1: GET não expõe evento pessoal alheio NEM evento de caso alheio ────────

async def test_listar_nao_expoe_evento_pessoal_nem_de_caso_alheio():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cli Agenda {uuid4().hex[:6]}")
        caso = await _criar_caso(db, cli, "Caso Agenda", resp_id=dono)
        d = date.today() + timedelta(days=5)
        pessoal = await _inserir_evento(
            db, resp=dono, data_evento=d, titulo="Consulta médica pessoal")
        de_caso = await _inserir_evento(
            db, resp=dono, data_evento=d, case_id=caso, titulo="Audiência do caso")
        # Evento do MESMO caso alheio, mas cujo responsável é "outro" — visível
        # a ele pela regra do responsável do EVENTO (padrão atividades.py).
        de_caso_resp_outro = await _inserir_evento(
            db, resp=outro, created_by=dono, data_evento=d, case_id=caso,
            titulo="Diligência delegada")
        await db.commit()
        try:
            u_dono = await _carregar_user(db, dono)
            u_outro = await _carregar_user(db, outro)
            u_socio = await _carregar_user(db, socio)

            # Advogado do caso vê o próprio pessoal + os eventos do caso.
            vistos_dono = _ids(await listar(page_size=500, db=db, cu=u_dono))
            assert {pessoal, de_caso, de_caso_resp_outro} <= vistos_dono
            # Gestão vê tudo.
            vistos_socio = _ids(await listar(page_size=500, db=db, cu=u_socio))
            assert {pessoal, de_caso, de_caso_resp_outro} <= vistos_socio
            # M1: advogado alheio ao caso NÃO vê o evento do caso (antes vazava
            # titulo/local/caso_titulo — contradizia atividades.py) nem o
            # pessoal de outro usuário; vê apenas o evento em que é responsável.
            vistos_outro = _ids(await listar(page_size=500, db=db, cu=u_outro))
            assert de_caso not in vistos_outro
            assert pessoal not in vistos_outro
            assert de_caso_resp_outro in vistos_outro
        finally:
            await _limpar(db, user_ids=[dono, outro, socio],
                          case_ids=[caso], client_ids=[cli])


# ── N2a: responsavel_id de terceiro exige gestão ────────────────────────────────

async def test_criar_para_terceiro_exige_gestao():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        await db.commit()
        d = date.today() + timedelta(days=6)
        try:
            u_adv = await _carregar_user(db, adv)
            u_socio = await _carregar_user(db, socio)

            # Advogado → agenda de terceiro: 403.
            with pytest.raises(HTTPException) as exc:
                await criar(EventoIn(titulo="Invasão", data_evento=d,
                                     responsavel_id=outro), db=db, cu=u_adv)
            assert exc.value.status_code == 403
            # Advogado → próprio (explícito e implícito): livre.
            assert (await criar(EventoIn(titulo="Meu", data_evento=d,
                                         responsavel_id=adv), db=db, cu=u_adv))["ok"]
            assert (await criar(EventoIn(titulo="Meu 2", data_evento=d),
                                db=db, cu=u_adv))["ok"]
            # Gestão → terceiro: livre.
            assert (await criar(EventoIn(titulo="Da gestão", data_evento=d,
                                         responsavel_id=outro), db=db, cu=u_socio))["ok"]
        finally:
            await _limpar(db, user_ids=[adv, outro, socio])


async def test_patch_transferencia_para_terceiro_exige_gestao():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        d = date.today() + timedelta(days=7)
        evt = await _inserir_evento(db, resp=adv, data_evento=d, titulo="Meu evento")
        await db.commit()
        try:
            u_adv = await _carregar_user(db, adv)
            u_socio = await _carregar_user(db, socio)

            # Dono (não-gestão) transfere p/ terceiro: 403.
            with pytest.raises(HTTPException) as exc:
                await atualizar(evt, EventoPatch(responsavel_id=outro), db=db, cu=u_adv)
            assert exc.value.status_code == 403
            # No-op (mantém o responsável atual) não bloqueia.
            assert (await atualizar(evt, EventoPatch(responsavel_id=adv),
                                    db=db, cu=u_adv))["ok"]
            # Gestão transfere: livre.
            assert (await atualizar(evt, EventoPatch(responsavel_id=outro),
                                    db=db, cu=u_socio))["ok"]
        finally:
            await _limpar(db, user_ids=[adv, outro, socio])


# ── N2b: conflito de agenda alheia vem censurado ────────────────────────────────

async def test_conflito_de_agenda_alheia_e_censurado_para_nao_gestao():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        criador = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        d = date.today() + timedelta(days=8)
        # Evento PESSOAL do terceiro — título/local sensíveis.
        await _inserir_evento(db, resp=outro, data_evento=d, hora="14:00",
                              titulo="Consulta psiquiátrica", local="Clínica X")
        # Evento cujo responsável é o terceiro mas o CRIADOR pode editar
        # (created_by) — legado de antes do gate N2a.
        evt = await _inserir_evento(db, resp=outro, created_by=criador,
                                    data_evento=d, hora="10:00", titulo="Reunião")
        await db.commit()
        try:
            u_criador = await _carregar_user(db, criador)
            u_socio = await _carregar_user(db, socio)

            # Criador (não-gestão) move p/ 14:00 → colide com a agenda do
            # TERCEIRO: existência/horário aparecem, título/local não.
            out = await atualizar(evt, EventoPatch(hora="14:00"), db=db, cu=u_criador)
            assert len(out["conflito_agenda"]) == 1
            c = out["conflito_agenda"][0]
            assert c["titulo"] == "Compromisso de outro usuário"
            assert c["local"] is None
            assert c["hora"].strip() == "14:00"          # horário preservado
            assert "id" in c                             # contrato (chaves) mantido
            # Gestão vê o conflito SEM censura.
            out2 = await atualizar(evt, EventoPatch(hora="14:00"), db=db, cu=u_socio)
            assert out2["conflito_agenda"][0]["titulo"] == "Consulta psiquiátrica"
            assert out2["conflito_agenda"][0]["local"] == "Clínica X"
        finally:
            await _limpar(db, user_ids=[criador, outro, socio])


# ── B1: auditoria de transferência e DELETE ─────────────────────────────────────

async def _audits(db, evento_id: str) -> list[dict]:
    rows = (await db.execute(text(
        "SELECT acao, detalhes FROM audit_logs "
        "WHERE entidade = 'agenda_eventos' AND registro_id = :rid "
        "ORDER BY created_at"
    ), {"rid": evento_id})).mappings().all()
    return [dict(r) for r in rows]


async def test_transferencia_e_delete_geram_audit_log():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        d = date.today() + timedelta(days=9)
        evt = await _inserir_evento(db, resp=adv, data_evento=d, titulo="Auditável")
        await db.commit()
        try:
            u_adv = await _carregar_user(db, adv)
            u_socio = await _carregar_user(db, socio)

            # PATCH sem troca de responsável NÃO audita (só a transferência).
            assert (await atualizar(evt, EventoPatch(titulo="Renomeado"),
                                    db=db, cu=u_adv))["ok"]
            assert await _audits(db, evt) == []
            # Transferência (gestão → terceiro) audita antigo → novo.
            assert (await atualizar(evt, EventoPatch(responsavel_id=outro),
                                    db=db, cu=u_socio))["ok"]
            logs = await _audits(db, evt)
            assert [l["acao"] for l in logs] == ["UPDATE"]
            assert adv in logs[0]["detalhes"] and outro in logs[0]["detalhes"]
            # DELETE (soft) audita.
            assert (await remover(evt, db=db, cu=u_socio))["ok"]
            logs = await _audits(db, evt)
            assert [l["acao"] for l in logs] == ["UPDATE", "DELETE"]
        finally:
            await _limpar(db, user_ids=[adv, outro, socio])


# ── B3: responsavel_id precisa existir em users ─────────────────────────────────

async def test_responsavel_inexistente_recusado_422():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        d = date.today() + timedelta(days=10)
        evt = await _inserir_evento(db, resp=socio, data_evento=d, titulo="Meu")
        await db.commit()
        fantasma = str(uuid4())
        try:
            u_socio = await _carregar_user(db, socio)

            # POST com responsavel_id fantasma → 422 claro (antes: evento órfão).
            with pytest.raises(HTTPException) as exc:
                await criar(EventoIn(titulo="Órfão", data_evento=d,
                                     responsavel_id=fantasma), db=db, cu=u_socio)
            assert exc.value.status_code == 422
            assert "usuário não encontrado" in exc.value.detail
            # PATCH transferindo p/ fantasma → 422 e evento intacto.
            with pytest.raises(HTTPException) as exc:
                await atualizar(evt, EventoPatch(responsavel_id=fantasma),
                                db=db, cu=u_socio)
            assert exc.value.status_code == 422
            resp_atual = (await db.execute(text(
                "SELECT responsavel_id FROM agenda_eventos WHERE id = :id"
            ), {"id": evt})).scalar()
            assert resp_atual == socio
        finally:
            await _limpar(db, user_ids=[socio])
