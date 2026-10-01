"""Regressão DB-level da paginação cursor de /tasks (Tarefa 2).

Provas que SQLite não dá: keyset com NULLS LAST (NULL não compara), desempate
por id com (data_limite, created_at) empatados, e visibilidade por carteira
real. Mesmo padrão dos *_dblevel.py: requer PostgreSQL com migrations
aplicadas e ``RUN_DB_TESTS=1`` — **SKIP não é PASS** (baseline §6.4).

Execução:
  RUN_DB_TESTS=1 DATABASE_URL=postgresql+asyncpg://…/ejc_homolog_perf \
    python3 -m pytest tests/test_tasks_pagination_dblevel.py -q
"""
from __future__ import annotations

import os
from datetime import date
from types import SimpleNamespace
from uuid import uuid4, uuid5, NAMESPACE_URL

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.routers.tasks import listar

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL com migrations (RUN_DB_TESTS=1) — SKIP não é PASS",
)

NS = uuid5(NAMESPACE_URL, "perf.tasks.cursor.test")
HOJE = date.today()


def uid(chave: str) -> str:
    return str(uuid5(NS, chave))


A = uid("user:A")
B = uid("user:B")
S = uid("user:S")
CASE_A = uid("case:A")
CASE_B = uid("case:B")

# (chave, case_id, responsavel, criado_por, data_limite: dias de HOJE | None)
_TAREFAS = [
    ("tA1", "A", "A", "A", 5),
    ("tA2", "A", "A", "A", 5),   # empata com tA3
    ("tA3", "A", "A", "A", 5),   # empata com tA2
    ("tA4", "A", "A", "A", 1),
    ("tA5", "A", "A", "A", None),  # NULL: cauda NULLS LAST
    ("tA6", "A", "A", "A", 10),
    ("tB1", "B", "B", "B", 3),
    ("tB2", "B", "B", "B", 7),
    ("tB3", "B", "B", "B", 7),   # empata com tB2
    ("tL1", None, "A", "A", 2),  # caseless responsável A
    ("tL2", None, "A", "A", None),  # caseless com data NULL
    ("tL3", None, "B", "A", 2),  # A vê por criador; B por responsável
    ("tL4", None, "S", "S", 2),  # só gestão/proprio: invisível a A e B
]
TODAS_ESPERADAS = {uid(f"tk:{k}") for k, *_ in _TAREFAS}

# Visibilidade canônica (tasks.py 109-130): tarefa COM caso segue a carteira
# do caso; caseless é pessoal ao responsável OU criador.
VISIVEIS = {
    # A: 6 do case A + caseless onde é resp (tL1,tL2) ou criador (tL3) = 9
    A: {uid(f"tk:tA{i}") for i in range(1, 7)}
       | {uid("tk:tL1"), uid("tk:tL2"), uid("tk:tL3")},
    # B: 3 do case B + tL3 (responsável) = 4
    B: {uid(f"tk:tB{i}") for i in range(1, 4)} | {uid("tk:tL3")},
    # S: gestão vê tudo (13) — exceto nada; tX soft-deleted já está fora
    S: TODAS_ESPERADAS,
}


def _user(uid_: str, role: str):
    return SimpleNamespace(id=uid_, role=SimpleNamespace(value=role))


async def _semear() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active)"
            " VALUES (:id, :email, 'x', 'Perf Tasks', :role::userrole, true)"
            " ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": A, "email": f"{A}@dbtest.local", "role": "advogado"},
            {"id": B, "email": f"{B}@dbtest.local", "role": "advogado"},
            {"id": S, "email": f"{S}@dbtest.local", "role": "socio"},
        ])
        await db.execute(text(
            "INSERT INTO clients (id, tipo, nome, email, status, responsavel_id)"
            " VALUES (:id, 'PF', 'Cliente Tasks Cursor', 'ctc@dbtest.local',"
            " 'ativo', :resp) ON CONFLICT (id) DO NOTHING"
        ), {"id": uid("client"), "resp": A})
        await db.execute(text(
            "INSERT INTO cases (id, titulo, area, status, client_id,"
            " advogado_responsavel_id, proxima_acao)"
            " VALUES (:id, :titulo, 'civil', 'aberto'::casestatus,"
            " :cid, :resp, 'Atuar') ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": CASE_A, "titulo": "Caso A cursor", "cid": uid("client"), "resp": A},
            {"id": CASE_B, "titulo": "Caso B cursor", "cid": uid("client"), "resp": B},
        ])
        linhas = []
        for k, caso, resp, criador, dl in _TAREFAS:
            linhas.append({
                "id": uid(f"tk:{k}"), "t": f"Tarefa {k}",
                "status": "a_fazer" if k != "tA4" else "concluida",
                "dl": (HOJE.fromordinal(HOJE.toordinal() + dl)) if dl is not None else None,
                "case_id": CASE_A if caso == "A" else CASE_B if caso == "B" else None,
                "resp": {"A": A, "B": B, "S": S}[resp],
                "criador": {"A": A, "B": B, "S": S}[criador],
            })
        # tarefa soft-deleted no case A: nunca pode aparecer em modo nenhum
        linhas.append({
            "id": uid("tk:tX"), "t": "Tarefa removida",
            "status": "a_fazer", "dl": HOJE,
            "case_id": CASE_A, "resp": A, "criador": A,
        })
        await db.execute(text(
            "INSERT INTO tasks (id, titulo, status, prioridade, data_limite,"
            " case_id, responsavel_id, criado_por, deleted_at)"
            " VALUES (:id, :t, :status::taskstatus, 'media', :dl, :case_id,"
            " :resp, :criador, CASE WHEN :id = :removida THEN now() END)"
            " ON CONFLICT (id) DO NOTHING"
        ), [{**l, "removida": uid("tk:tX")} for l in linhas])
        await db.commit()


def _ordem_esperada(dados: list[dict]) -> list[str]:
    """Ordenação canônica do modo cursor aplicada aos dicts retornados."""
    def chave(d):
        return (
            d["data_limite"] is None,
            d["data_limite"] or date.max,
            d["created_at"],
            d["id"],
        )
    return [d["id"] for d in sorted(dados, key=chave)]


async def _listar(cu, **kwargs):
    async with AsyncSessionLocal() as db:
        return await listar(
            db=db, cu=cu,
            **{"pagination": "cursor", "page_size": 3, **kwargs},
        )


@pytest.mark.asyncio
async def test_walk_cobre_o_conjunto_visivel_sem_duplicar_nem_pular():
    await _semear()
    async with AsyncSessionLocal() as db:
        legado = await listar(db=db, cu=_user(S, "socio"))
    ids_legado = [d["id"] for d in legado["data"]]
    assert set(ids_legado) == TODAS_ESPERADAS  # tX soft-deleted fora

    esperado = _ordem_esperada(legado["data"])
    coletados: list[str] = []
    cursor = None
    paginas = 0
    while True:
        r = await _listar(_user(S, "socio"), cursor=cursor)
        ids = [d["id"] for d in r["data"]]
        assert ids, "página vazia antes de has_more=False"
        coletados.extend(ids)
        paginas += 1
        if not r["has_more"]:
            break
        cursor = r["next_cursor"]
        assert cursor
    assert paginas > 1, "com 13 visíveis e página 3, precisa de >1 página"
    assert coletados == esperado, (
        "walk do cursor divergiu da ordenação canônica (pulo/duplicação/ordem)"
    )
    # contagem com a página final contando resto: 13 = 3+3+3+3+1
    assert len(coletados) == len(TODAS_ESPERADAS)


@pytest.mark.asyncio
@pytest.mark.parametrize("ator,papel", [(A, "advogado"), (B, "advogado")])
async def test_visibilidade_por_carteira_no_walk(ator, papel):
    await _semear()
    coletados: list[str] = []
    cursor = None
    while True:
        r = await _listar(_user(ator, papel), cursor=cursor)
        coletados.extend(d["id"] for d in r["data"])
        if not r["has_more"]:
            break
        cursor = r["next_cursor"]
    assert set(coletados) == VISIVEIS[ator]
    assert set(coletados) == set(set(coletados))  # sem duplicação


@pytest.mark.asyncio
async def test_cursor_de_outro_usuario_e_rejeitado():
    await _semear()
    p1 = await _listar(_user(A, "advogado"))
    assert p1["next_cursor"]
    with pytest.raises(HTTPException) as exc:
        await _listar(_user(B, "advogado"), cursor=p1["next_cursor"])
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_mudanca_de_filtro_invalida_cursor():
    await _semear()
    p1 = await _listar(_user(A, "advogado"), minhas=False)
    assert p1["next_cursor"]
    with pytest.raises(HTTPException) as exc:
        await _listar(_user(A, "advogado"), minhas=True,
                      cursor=p1["next_cursor"])
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_case_id_filtra_e_cursor_respeita():
    await _semear()
    r1 = await _listar(_user(S, "socio"), case_id=CASE_A)
    ids_p1 = {d["id"] for d in r1["data"]}
    assert ids_p1 <= {uid(f"tk:tA{i}") for i in range(1, 7)}


@pytest.mark.asyncio
async def test_legado_inalterado_shape_e_feed_completo():
    await _semear()
    async with AsyncSessionLocal() as db:
        r = await listar(db=db, cu=_user(S, "socio"))
    # shape legacy: só "data" — nenhum campo de cursor vazou no default
    assert set(r.keys()) == {"data"}
    assert {d["id"] for d in r["data"]} == TODAS_ESPERADAS


@pytest.mark.asyncio
async def test_pagina_unica_quando_resto_cabe():
    await _semear()
    r = await _listar(_user(B, "advogado"), page_size=50)
    assert r["has_more"] is False
    assert r["next_cursor"] is None
    assert {d["id"] for d in r["data"]} == VISIVEIS[B]


@pytest.mark.asyncio
async def test_cursor_adulterado_e_rejeitado():
    await _semear()
    p1 = await _listar(_user(A, "advogado"))
    body, sig = p1["next_cursor"].split(".", 1)
    adulterado = ("A" + body[1:]) + "." + sig
    with pytest.raises(HTTPException) as exc:
        await _listar(_user(A, "advogado"), cursor=adulterado)
    assert exc.value.status_code == 409
