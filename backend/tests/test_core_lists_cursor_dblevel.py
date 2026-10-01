"""Regressão DB-level do cursor nas 4 listas — cases/clients/deadlines/documents (Tarefa 5).

Provas com PostgreSQL real (RUN_DB_TESTS=1 — **SKIP não é PASS**):
  • walk página a página == ordem legacy (created_at DESC / data_prazo ASC,
    com desempate por id) — sem pulo, sem duplicação, mesmo com timestamps
    e datas empatados (o seed força empates);
  • response cursor NÃO finge total (sem chaves total/page) e o offset
    default permanece intacto (com total real);
  • cursor de outro usuário ou com filtro diferente → 409.
"""
from __future__ import annotations

import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid5, NAMESPACE_URL

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.routers.cases import listar as listar_cases
from app.routers.clients import listar as listar_clients
from app.routers.deadlines import listar as listar_deadlines
from app.routers.documents import listar as listar_documents

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL com migrations (RUN_DB_TESTS=1) — SKIP não é PASS",
)

NS = uuid5(NAMESPACE_URL, "perf.corelists.cursor.test")


def uid(chave: str) -> str:
    return str(uuid5(NS, chave))


A = uid("user:A")
B = uid("user:B")
S = uid("user:S")
CID = uid("client")
CASE_A = uid("case:A")
CASE_B = uid("case:B")


def _user(uid_: str, role: str):
    return SimpleNamespace(id=uid_, role=SimpleNamespace(value=role))


async def _semear() -> None:
    from datetime import date

    hoje = date.today()
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active)"
            " VALUES (:id, :email, 'x', 'Perf Listas', :role::userrole, true)"
            " ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": A, "email": f"{A}@dbtest.local", "role": "advogado"},
            {"id": B, "email": f"{B}@dbtest.local", "role": "advogado"},
            {"id": S, "email": f"{S}@dbtest.local", "role": "socio"},
        ])
        await db.execute(text(
            "INSERT INTO clients (id, tipo, nome, email, status, responsavel_id)"
            " VALUES (:id, 'PF', 'Cliente Listas', 'listas@dbtest.local', 'ativo', :resp)"
            " ON CONFLICT (id) DO NOTHING"
        ), {"id": CID, "resp": A})
        # 5 casos por carteira — created_at idêntico (mesma transação) força o
        # desempate por id na ordenação do cursor.
        casos = [{"id": uid(f"case:A{i}"), "resp": A} for i in range(5)]
        casos += [{"id": uid(f"case:B{i}"), "resp": B} for i in range(5)]
        await db.execute(text(
            "INSERT INTO cases (id, titulo, area, status, client_id,"
            " advogado_responsavel_id, proxima_acao)"
            " VALUES (:id, :titulo, 'civil', 'aberto'::casestatus, :cid,"
            " :resp, 'Atuar') ON CONFLICT (id) DO NOTHING"
        ), [{"id": c["id"], "titulo": f"Caso {c['id'][-6:]}",
             "cid": CID, "resp": c["resp"]} for c in casos])
        # 8 prazos com a MESMA data (tie test) na carteira A
        await db.execute(text(
            "INSERT INTO deadlines (id, titulo, tipo, prioridade, status,"
            " data_prazo, case_id, responsavel_id, confirmado)"
            " VALUES (:id, :t, 'processual', 'media', 'pendente'::deadlinestatus,"
            " :dp, :case_id, :resp, true) ON CONFLICT (id) DO NOTHING"
        ), [{"id": uid(f"dl:{i}"), "t": f"Prazo {i}", "dp": hoje,
             "case_id": CASE_A, "resp": A} for i in range(8)])
        # 6 documentos no caso A
        await db.execute(text(
            "INSERT INTO documents (id, titulo, filename, filepath,"
            " confidencialidade, case_id, uploaded_by)"
            " VALUES (:id, :t, :fn, :fp, 'normal'::docconfidencialidade,"
            " :case_id, :up) ON CONFLICT (id) DO NOTHING"
        ), [{"id": uid(f"doc:{i}"), "t": f"Doc {i}", "fn": f"d{i}.pdf",
             "fp": f"/p/d{i}.pdf", "case_id": CASE_A, "up": A}
            for i in range(6)])
        await db.commit()


async def _walk(listar, cu, *, page_size=2, order_key, **kwargs):
    coletados: list[dict] = []
    cursor = None
    while True:
        async with AsyncSessionLocal() as db:
            r = await listar(db=db, cu=cu, cursor=cursor,
                             pagination="cursor", page_size=page_size, **kwargs)
        assert r["has_more"] in (True, False)
        assert r["next_cursor"] is not None or not r["has_more"]
        coletados.extend(r["data"])
        if not r["has_more"]:
            break
        cursor = r["next_cursor"]
    ids = [order_key(d) for d in coletados]
    assert len(ids) == len(set(ids)), "duplicação no walk do cursor"
    return coletados, r


@pytest.mark.asyncio
async def test_walk_cases_igual_ordem_legacy_sem_duplicar():
    await _semear()
    async with AsyncSessionLocal() as db:
        legado = await listar_cases(db=db, cu=_user(S, "socio"))
    esperado = [d["id"] for d in sorted(
        legado["data"],
        key=lambda d: (d["created_at"], d["id"]), reverse=True,
    )]
    coletados, ultima = await _walk(
        listar_cases, _user(S, "socio"), order_key=lambda d: d["id"])
    # shape do cursor: sem total/page falsificados
    assert "total" not in ultima and "page" not in ultima
    assert [d["id"] for d in coletados] == esperado


@pytest.mark.asyncio
async def test_walk_clients_igual_ordem_legacy():
    await _semear()
    async with AsyncSessionLocal() as db:
        legado = await listar_clients(db=db, cu=_user(S, "socio"))
    esperado = [d["id"] for d in sorted(
        legado["data"], key=lambda d: (d["created_at"], d["id"]), reverse=True)]
    coletados, _ = await _walk(
        listar_clients, _user(S, "socio"), order_key=lambda d: d["id"])
    assert [d["id"] for d in coletados] == esperado


@pytest.mark.asyncio
async def test_walk_deadlines_com_datas_empatadas():
    await _semear()
    async with AsyncSessionLocal() as db:
        legado = await listar_deadlines(db=db, cu=_user(S, "socio"),
                                        status_f="all")
    esperado = [d["id"] for d in sorted(
        legado["data"], key=lambda d: (d["data_prazo"], d["id"]))]
    coletados, _ = await _walk(
        listar_deadlines, _user(S, "socio"), order_key=lambda d: d["id"],
        status_f="all")
    assert len(coletados) == 8
    assert [d["id"] for d in coletados] == esperado


@pytest.mark.asyncio
async def test_walk_documents_igual_ordem_legacy():
    await _semear()
    async with AsyncSessionLocal() as db:
        legado = await listar_documents(db=db, cu=_user(S, "socio"))
    esperado = [d["id"] for d in sorted(
        legado["data"], key=lambda d: (d["created_at"], d["id"]), reverse=True)]
    coletados, _ = await _walk(
        listar_documents, _user(S, "socio"), order_key=lambda d: d["id"])
    assert len(coletados) == 6
    assert [d["id"] for d in coletados] == esperado


@pytest.mark.asyncio
async def test_cursor_de_outro_usuario_e_filtro_mudado_rejeitados():
    await _semear()
    async with AsyncSessionLocal() as db:
        p1 = await listar_cases(db=db, cu=_user(A, "advogado"),
                                pagination="cursor", page_size=2)
    assert p1["next_cursor"]
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await listar_cases(db=db, cu=_user(B, "advogado"),
                               pagination="cursor", page_size=2,
                               cursor=p1["next_cursor"])
        assert exc.value.status_code == 409
        # filtro mudou → 409
        with pytest.raises(HTTPException) as exc2:
            await listar_cases(db=db, cu=_user(A, "advogado"),
                               pagination="cursor", page_size=2,
                               status_f="encerrado",
                               cursor=p1["next_cursor"])
        assert exc2.value.status_code == 409


@pytest.mark.asyncio
async def test_offset_default_intacto_com_total_real():
    await _semear()
    async with AsyncSessionLocal() as db:
        r = await listar_cases(db=db, cu=_user(S, "socio"))
    assert set(r.keys()) == {"data", "total", "page", "page_size"}
    assert r["total"] == 10 and r["page"] == 1
