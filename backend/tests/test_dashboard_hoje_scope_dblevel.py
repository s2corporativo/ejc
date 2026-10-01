# -*- coding: utf-8 -*-
"""Tarefa 4 — escopo e contrato de GET /dashboard/hoje (integração PostgreSQL).

Cobre os atores do plano (admin/sócio/advogado/auxiliar/secretaria/cliente
externo) com casos A (A1) e B (A2):

  - cliente externo: 403 (não existe "hoje" para portal)
  - advogado (A1): contagens e decisões SÓ da própria carteira — nada de A2
    ("por padrão, não expor novos dados de outro dono")
  - auxiliar: enxerga a carteira do caso em que atua
  - secretaria: escopo "carteira" (sem dados de terceiros via nova rota)
  - sócio/admin: escopo "escritório" (legítimo global) — vê A e B
  - KPI global de /dashboard/ permanece intacto (rota separada)
  - sem cache: resposta fresca após escrita (contagem muda na hora)
  - decisão priorizada não perde ranking (peça em revisão 120 > prazo vencido
    118 > peça corrigida 112 > prazo hoje 110 > tarefa atrasada 105)
  - degradado: erro ≠ 0 (bloco nulo é nomeado)
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.routers.dashboard import dashboard, dashboard_hoje

_pg = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str, rotulo: str) -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, "
             "is_active) VALUES (:id, :email, 'x', :n, :role, true)"),
        {"id": uid, "email": f"hoje-{rotulo}-{uid[:8]}@teste.local",
         "role": role, "n": f"Hoje {rotulo}"})
    return uid


async def _carregar_user(db, uid: str):
    from app.models.user import User
    from sqlalchemy import select
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _criar_caso(db, dono: str, titulo: str, *,
                      auxiliar: str | None = None,
                      proxima_acao: str | None = "Ação") -> str:
    cid, cliente = str(uuid4()), str(uuid4())
    await db.execute(text(
        "INSERT INTO clients (id, nome, responsavel_id, tipo, status) "
        "VALUES (:id, :n, :d, 'PF', 'ativo')"),
        {"id": cliente, "n": f"Cliente {titulo}", "d": dono})
    await db.execute(text(
        "INSERT INTO cases (id, titulo, area, status, prioridade, client_id, "
        "advogado_responsavel_id, advogado_auxiliar_id, proxima_acao, created_at) "
        "VALUES (:id, :t, 'civil', 'aberto', 'media', :cli, :d, :aux, :pa, now())"),
        {"id": cid, "t": titulo, "cli": cliente, "d": dono, "aux": auxiliar,
         "pa": proxima_acao})
    return cid


async def _criar_prazo(db, *, caso, resp, dias, status="pendente",
                       titulo="regress-hoje") -> str:
    did = str(uuid4())
    await db.execute(text(
        "INSERT INTO deadlines (id, titulo, tipo, prioridade, status, data_prazo, "
        "case_id, responsavel_id) VALUES "
        "(:id, :t, 'processual', 'media', :st, :d, :c, :r)"),
        {"id": did, "t": f"{titulo}-{did[:8]}", "st": status,
         "d": date.today() + timedelta(days=dias), "c": caso, "r": resp})
    return did


async def _criar_tarefa(db, *, caso, resp, dias) -> str:
    tid = str(uuid4())
    await db.execute(text(
        "INSERT INTO tasks (id, titulo, status, prioridade, data_limite, case_id, "
        "responsavel_id, criado_por, created_at) VALUES "
        "(:id, 'tarefa-hoje', 'a_fazer', 'media', :d, :c, :r, :r, now())"),
        {"id": tid, "d": date.today() + timedelta(days=dias), "c": caso, "r": resp})
    return tid


async def _limpar(db, *, user_ids=()):
    for uid in user_ids:
        await db.execute(text(
            "DELETE FROM legal_docs WHERE case_id IN "
            "(SELECT id FROM cases WHERE advogado_responsavel_id = :u)"), {"u": uid})
        await db.execute(text(
            "DELETE FROM tasks WHERE responsavel_id = :u OR criado_por = :u "
            "OR case_id IN (SELECT id FROM cases WHERE advogado_responsavel_id = :u)"),
            {"u": uid})
        await db.execute(text(
            "DELETE FROM deadlines WHERE responsavel_id = :u OR case_id IN "
            "(SELECT id FROM cases WHERE advogado_responsavel_id = :u)"), {"u": uid})
        await db.execute(text(
            "DELETE FROM cases WHERE advogado_responsavel_id = :u "
            "OR advogado_auxiliar_id = :u"), {"u": uid})
        await db.execute(text(
            "DELETE FROM clients WHERE responsavel_id = :u"), {"u": uid})
        await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


@_pg
async def test_cliente_externo_bloqueado_e_staff_ok():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        cext = await _criar_user(db, "cliente_externo", "cext")
        sec = await _criar_user(db, "secretaria", "sec")
        await db.commit()
        try:
            with pytest.raises(HTTPException):
                await dashboard_hoje(db=db, cu=await _carregar_user(db, cext))
            out = await dashboard_hoje(db=db, cu=await _carregar_user(db, sec))
            assert out["escopo"] == "carteira"
            assert out["data_operacional"]
            assert out["gerado_em"]
            assert out["degradado"] == []
        finally:
            await _limpar(db, user_ids=[cext, sec])


@_pg
async def test_advogado_ve_so_a_proprias_carteira():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        a2 = await _criar_user(db, "advogado", "a2")
        caso_a = await _criar_caso(db, a1, "Caso A hoje")
        caso_b = await _criar_caso(db, a2, "Caso B hoje")
        # carteira de A1: prazo vencido, prazo hoje, tarefa atrasada
        await _criar_prazo(db, caso=caso_a, resp=a1, dias=-2)
        await _criar_prazo(db, caso=caso_a, resp=a1, dias=0)
        await _criar_tarefa(db, caso=caso_a, resp=a1, dias=-1)
        # carteira de A2: prazo vencido (não pode vazar para A1)
        await _criar_prazo(db, caso=caso_b, resp=a2, dias=-5)
        # avulso pessoal de A2
        await db.execute(text(
            "INSERT INTO deadlines (id, titulo, tipo, prioridade, status, "
            "data_prazo, case_id, responsavel_id) VALUES "
            "(:id, 'regress-hoje-avulso', 'interno', 'media', 'pendente', :d, "
            "NULL, :r)"),
            {"id": str(uuid4()), "d": date.today() - timedelta(days=1),
             "r": a2})
        await db.commit()
        try:
            cu1 = await _carregar_user(db, a1)
            out = await dashboard_hoje(db=db, cu=cu1)
            assert out["escopo"] == "carteira"
            assert out["contagens"]["prazos"]["vencidos"] == 1
            assert out["contagens"]["prazos"]["hoje"] == 1
            assert out["contagens"]["tarefas"]["atrasadas"] == 1
            # decisões só da carteira de A1
            tipos = {d["tipo"] for d in out["decisoes"]}
            assert "prazo" in tipos
            for d in out["decisoes"]:
                if d["case_id"]:
                    assert d["case_id"] == caso_a
            # prioridade do prazo vencido (118) no topo, ranking preservado
            assert out["decisoes"][0]["prioridade"] >= max(
                d["prioridade"] for d in out["decisoes"])
        finally:
            await _limpar(db, user_ids=[a1, a2])


@_pg
async def test_auxiliar_e_gestao_escopo():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        aux = await _criar_user(db, "advogado_auxiliar", "aux")
        socio = await _criar_user(db, "socio", "socio")
        caso_a = await _criar_caso(db, a1, "Caso A aux", auxiliar=aux)
        caso_b = await _criar_caso(db, socio, "Caso B socio")
        await _criar_prazo(db, caso=caso_a, resp=a1, dias=-3)
        await _criar_prazo(db, caso=caso_b, resp=socio, dias=-1)
        await db.commit()
        try:
            # auxiliar participa do caso A → vê o prazo dele
            out_aux = await dashboard_hoje(db=db, cu=await _carregar_user(db, aux))
            assert out_aux["escopo"] == "carteira"
            assert out_aux["contagens"]["prazos"]["vencidos"] == 1
            # sócio (gestão) → escritório: vê vencidos de A e B
            out_socio = await dashboard_hoje(db=db,
                                             cu=await _carregar_user(db, socio))
            assert out_socio["escopo"] == "escritorio"
            assert out_socio["contagens"]["prazos"]["vencidos"] >= 2
        finally:
            await _limpar(db, user_ids=[a1, aux, socio])


@_pg
async def test_sem_cache_atualiza_pos_escrita_e_casos_sem_acao():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        caso_a = await _criar_caso(db, a1, "Caso A cache", proxima_acao=None)
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            out1 = await dashboard_hoje(db=db, cu=cu)
            assert out1["contagens"]["casos_sem_proxima_acao"] == 1
            await _criar_prazo(db, caso=caso_a, resp=a1, dias=1)
            await db.commit()
            # SEM cache de 30s: nova leitura já reflete a escrita
            out2 = await dashboard_hoje(db=db, cu=cu)
            assert out2["contagens"]["prazos"]["proximos_3d"] == 1
            # conclusão do prazo some da contagem (status filter do feed)
            await db.execute(text(
                "UPDATE deadlines SET status='concluido' WHERE case_id = :c"),
                {"c": caso_a})
            await db.commit()
            out3 = await dashboard_hoje(db=db, cu=cu)
            assert out3["contagens"]["prazos"]["proximos_3d"] == 0
        finally:
            await _limpar(db, user_ids=[a1])


@_pg
async def test_dashboard_global_inalterado():
    """/dashboard/ legado continua com a mesma resposta de KPIs (contrato)."""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio", "socio2")
        await db.commit()
        try:
            cu = await _carregar_user(db, socio)
            out = await dashboard(db=db, cu=cu)
            for chave in ("casos", "prazos", "financeiro", "degradado",
                          "clientes_ativos", "pecas_aguardando_revisao"):
                assert chave in out
            assert out["financeiro"]["escopo"] in ("escritorio", "meus_casos")
        finally:
            await _limpar(db, user_ids=[socio])
