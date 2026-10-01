"""Regressão DB-level do cursor + resumo da Central (Tarefa 3).

Prova os gates da Tarefa 3 com PostgreSQL real:
  • walk do cursor == conjunto visível na ordenação (data NULLS LAST, tipo, id);
  • enriquecimento em lote: prazo carrega confirmado/ciencia_confirmada e
    agenda carrega hora/local — os botões Confirmar/Dar ciência (e o subtítulo
    de hora/local) não podem se perder com a paginação;
  • /resumo conta o conjunto visível (anti-auto-zerar) com o MESMO predicado
    de visibilidade do feed, e respeita escopo case_id;
  • mudança de apenas_pendentes invalida o cursor (409).
Requer ``RUN_DB_TESTS=1`` — **SKIP não é PASS** (baseline §6.4).
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid5, NAMESPACE_URL

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.routers.atividades import listar_atividades, resumo_atividades

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL com migrations (RUN_DB_TESTS=1) — SKIP não é PASS",
)

NS = uuid5(NAMESPACE_URL, "perf.atividades.cursor.test")
HOJE = date.today()


def uid(chave: str) -> str:
    return str(uuid5(NS, chave))


A = uid("user:A")
B = uid("user:B")
CASE_A = uid("case:A")
CASE_B = uid("case:B")


def _user(uid_: str, role: str):
    return SimpleNamespace(id=uid_, role=SimpleNamespace(value=role))


async def _semear() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active)"
            " VALUES (:id, :email, 'x', 'Perf Ativ', :role::userrole, true)"
            " ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": A, "email": f"{A}@dbtest.local", "role": "advogado"},
            {"id": B, "email": f"{B}@dbtest.local", "role": "advogado"},
        ])
        await db.execute(text(
            "INSERT INTO clients (id, tipo, nome, email, status, responsavel_id)"
            " VALUES (:id, 'PF', 'Cliente Ativ Cursor', 'cac@dbtest.local',"
            " 'ativo', :resp) ON CONFLICT (id) DO NOTHING"
        ), {"id": uid("client"), "resp": A})
        await db.execute(text(
            "INSERT INTO cases (id, titulo, area, status, client_id,"
            " advogado_responsavel_id, proxima_acao)"
            " VALUES (:id, :titulo, 'civil', 'aberto'::casestatus,"
            " :cid, :resp, 'Atuar') ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": CASE_A, "titulo": "Caso A atividades", "cid": uid("client"), "resp": A},
            {"id": CASE_B, "titulo": "Caso B atividades", "cid": uid("client"), "resp": B},
        ])
        # ── Prazos (carteira A): pendentes nas janelas de urgência ──────
        await db.execute(text(
            "INSERT INTO deadlines (id, titulo, tipo, prioridade, status,"
            " data_prazo, case_id, responsavel_id, confirmado, ciencia_confirmada)"
            " VALUES (:id, :t, 'processual', 'media', 'pendente'::deadlinestatus,"
            " :dp, :case_id, :resp, :conf, :ciencia)"
            " ON CONFLICT (id) DO NOTHING"
        ), [
            # vencido (−2 dias); rascunho IA NÃO confirmado (prova do botão)
            {"id": uid("dl:vencido"), "t": "Prazo vencido A", "dp": HOJE - timedelta(days=2),
             "case_id": CASE_A, "resp": A, "conf": False, "ciencia": False},
            {"id": uid("dl:critico"), "t": "Prazo crítico A", "dp": HOJE + timedelta(days=2),
             "case_id": CASE_A, "resp": A, "conf": True, "ciencia": True},
            {"id": uid("dl:atencao"), "t": "Prazo atenção A", "dp": HOJE + timedelta(days=6),
             "case_id": CASE_A, "resp": A, "conf": True, "ciencia": False},
            # case B (invisível para A)
            {"id": uid("dl:B"), "t": "Prazo B", "dp": HOJE - timedelta(days=1),
             "case_id": CASE_B, "resp": B, "conf": False, "ciencia": False},
            # concluído: fora do resumo pendentes e do feed apenas_pendentes
            {"id": uid("dl:ok"), "t": "Prazo concluído A", "dp": HOJE - timedelta(days=9),
             "case_id": CASE_A, "resp": A, "conf": True, "ciencia": True},
        ])
        # ── Tarefas (caseless pessoal + de caso) ────────────────────────
        await db.execute(text(
            "INSERT INTO tasks (id, titulo, status, prioridade, data_limite,"
            " case_id, responsavel_id, criado_por)"
            " VALUES (:id, :t, 'a_fazer'::taskstatus, 'media', :dl, :case_id,"
            " :resp, :criador) ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": uid("tk:caseless"), "t": "Tarefa avulsa A", "dl": HOJE + timedelta(days=1),
             "case_id": None, "resp": A, "criador": A},
            {"id": uid("tk:A"), "t": "Tarefa caso A", "dl": HOJE + timedelta(days=30),
             "case_id": CASE_A, "resp": A, "criador": A},
        ])
        # ── Agenda (prova hora/local no enriquecimento) ─────────────────
        await db.execute(text(
            "INSERT INTO agenda_eventos (id, titulo, tipo, data_evento, hora,"
            " local, case_id, responsavel_id, concluido, created_by)"
            " VALUES (:id, :t, 'audiencia', :de, '10:00', 'Sala 1',"
            " :case_id, :resp, false, :resp)"
            " ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": uid("ag:A"), "t": "Audiência A", "de": HOJE + timedelta(days=5),
             "case_id": CASE_A, "resp": A},
        ])
        # ── DJEN (intimação pendente na carteira de A) ──────────────────
        await db.execute(text(
            "INSERT INTO djen_comunicacoes (id, comunicacao_id_externo,"
            " advogado_id, data_disponibilizacao, processada, case_id,"
            " tipo_comunicacao, texto_resumo)"
            " VALUES (:id, :ext, :adv, :dd, false, :case_id, 'intimacao', 'Resumo')"
            " ON CONFLICT (id) DO NOTHING"
        ), [{"id": uid("dj:A"), "ext": f"ATIV-{A[:8]}",
             "adv": A, "dd": HOJE, "case_id": CASE_A}])
        await db.commit()


def _ordem_esperada(dados: list[dict]) -> list[str]:
    def chave(d):
        return (
            d["date"] is None,
            d["date"] or "9999-12-31",
            d["tipo"],
            d["id"],
        )
    return [d["id"] for d in sorted(dados, key=chave)]


async def _listar(cu, **kwargs):
    async with AsyncSessionLocal() as db:
        return await listar_atividades(db=db, cu=cu, **kwargs)


async def _resumo(cu, **kwargs):
    async with AsyncSessionLocal() as db:
        return await resumo_atividades(db=db, cu=cu, **kwargs)


@pytest.mark.asyncio
async def test_walk_cursor_cobre_feed_visivel_com_enriquecimento():
    await _semear()
    # feed completo (legado) como referência — pendentes de toda a carteira A
    legado = await _listar(_user(A, "advogado"), apenas_pendentes=False)
    esperado = _ordem_esperada(legado["data"])

    coletados: list[dict] = []
    cursor = None
    while True:
        r = await _listar(_user(A, "advogado"), apenas_pendentes=False,
                          pagination="cursor", page_size=2, cursor=cursor)
        assert r["data"], "página vazia antes de has_more=False"
        coletados.extend(r["data"])
        if not r["has_more"]:
            break
        cursor = r["next_cursor"]
        assert cursor
    assert [d["id"] for d in coletados] == esperado, "walk divergiu (pulo/ordem)"

    # ── GATE: botões/subtítulos preservados no modo cursor ────────────
    por_id = {d["id"]: d for d in coletados}
    prazo = por_id[uid("dl:vencido")]
    assert prazo["confirmado"] is False, "Confirmar sumiria sem confirmado"
    assert prazo["ciencia_confirmada"] is False, "Dar ciência sumiria sem ciência"
    evento = por_id[uid("ag:A")]
    assert evento["hora"] == "10:00" and evento["local"] == "Sala 1"


@pytest.mark.asyncio
async def test_resumo_bate_com_o_feed_e_respeita_escopo_e_visibilidade():
    await _semear()
    rA = await _resumo(_user(A, "advogado"), apenas_pendentes=True)
    # visível a A (pendentes): 3 prazos case A + tarefa caseless (dl=+1,
    # normal) + tarefa case A (+30, normal) + agenda (+5, atencao) + djen
    # (hoje, critico) → vencido=1, critico=2 (prazo +2 e djen), atencao=2
    # (prazo +6 e agenda +5), normal=2 (tarefas +1/+30)
    assert rA["vencido"] == 1
    assert rA["critico"] == 2
    assert rA["atencao"] == 2
    assert rA["normal"] == 2
    assert rA["pendentes"] == 7
    # case B: ZERO para A (visibilidade) — sem cross-user
    rB_para_A = await _resumo(_user(A, "advogado"), case_id=CASE_B)
    assert rB_para_A["pendentes"] == 0
    # escopo case A: exclui caseless (sem case) e djen do caso A? djen tem
    # case A → entra; caseless sai.
    rA_escopo = await _resumo(_user(A, "advogado"), case_id=CASE_A)
    assert rA_escopo["vencido"] == 1 and rA_escopo["critico"] == 2
    # B não vê nada de A
    rB = await _resumo(_user(B, "advogado"))
    assert rB["pendentes"] == 1  # só o prazo vencido do case B


@pytest.mark.asyncio
async def test_resumo_concluidos_fora_com_apenas_pendentes_false_voltam():
    await _semear()
    todos = await _resumo(_user(A, "advogado"), apenas_pendentes=False)
    pend = await _resumo(_user(A, "advogado"), apenas_pendentes=True)
    assert todos["pendentes"] == pend["pendentes"] + 1  # + prazo concluído


@pytest.mark.asyncio
async def test_mudanca_de_apenas_pendentes_invalida_cursor():
    await _semear()
    p1 = await _listar(_user(A, "advogado"), apenas_pendentes=False,
                       pagination="cursor", page_size=2)
    assert p1["next_cursor"]
    with pytest.raises(HTTPException) as exc:
        await _listar(_user(A, "advogado"), apenas_pendentes=True,
                      pagination="cursor", page_size=2,
                      cursor=p1["next_cursor"])
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_legado_inalterado_sem_enriquecimento_no_feed_completo():
    await _semear()
    legado = await _listar(_user(A, "advogado"), apenas_pendentes=False)
    assert set(legado.keys()) == {"data"}
    # shape legacy: sem campos de cursor nem enriquecimento (comportamento
    # atual preservado — rollback do frontend segue funcionando)
    item = legado["data"][0]
    assert "confirmado" not in item and "hora" not in item
    assert "next_cursor" not in legado
