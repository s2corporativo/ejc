"""GET /cases/{case_id}/partes — gate de ownership (row-level).

Regressão coberta: a listagem devolvia PII (nome, CPF/CNPJ, e-mail, telefone,
OAB) de partes de QUALQUER caso para qualquer usuário interno autenticado —
POST/DELETE já usavam verificar_acesso_caso, o GET não.

Postgres é OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: chama o handler
direto com `AsyncSessionLocal`). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


# ── Helpers de fixture (SQL cru, como nos demais *_dblevel.py) ───────────────

async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Partes Teste', :role, true)"),
        {"id": uid, "email": f"partes-{uid[:8]}@teste.local", "role": role},
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


async def _criar_caso(db, client_id: str, titulo: str,
                      resp_id: str | None = None) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "advogado_responsavel_id) VALUES "
             "(:id, :titulo, 'civil', 'em_instrucao', :cid, :resp)"),
        {"id": case_id, "titulo": titulo, "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _criar_parte(db, case_id: str, nome: str,
                       cpf_cnpj: str | None = None) -> None:
    await db.execute(
        text("INSERT INTO case_partes (case_id, tipo, nome, cpf_cnpj, ativo) "
             "VALUES (:cid, 'autor', :nome, :doc, true)"),
        {"cid": case_id, "nome": nome, "doc": cpf_cnpj},
    )


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM case_partes WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    """Evita 'Event loop is closed' entre testes async (loop por função)."""
    yield
    from app.core.database import engine
    await engine.dispose()


# ── Testes ────────────────────────────────────────────────────────────────────

async def test_listar_partes_respeita_ownership():
    from app.core.database import AsyncSessionLocal
    from app.routers.case_partes import listar_partes

    tok = f"Zzp{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        resp_adv = await _criar_user(db, "advogado")
        outro_adv = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Partes {tok}")
        caso = await _criar_caso(db, cli, f"Caso partes {tok}", resp_id=resp_adv)
        await _criar_parte(db, caso, f"Parte Autora {tok}", cpf_cnpj="153.509.460-56")
        await db.commit()
        try:
            # Responsável do caso vê as partes (documento completo incluso).
            partes = await listar_partes(caso, db, await _carregar_user(db, resp_adv))
            assert [p["nome"] for p in partes] == [f"Parte Autora {tok}"]
            assert partes[0]["cpf_cnpj"] == "153.509.460-56"

            # Gestão (socio+) vê qualquer caso.
            assert len(await listar_partes(caso, db, await _carregar_user(db, socio))) == 1

            # Advogado SEM vínculo com o caso → 403 (não vaza PII).
            with pytest.raises(HTTPException) as exc:
                await listar_partes(caso, db, await _carregar_user(db, outro_adv))
            assert exc.value.status_code == 403

            # Caso inexistente → 404.
            with pytest.raises(HTTPException) as exc2:
                await listar_partes(str(uuid4()), db, await _carregar_user(db, socio))
            assert exc2.value.status_code == 404
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv, socio], client_ids=[cli])


async def test_listar_partes_caso_sem_responsavel_so_gestao():
    """Caso sem responsável NEM auxiliar: o anti-lockout agora é a GESTÃO
    (socio+), não "qualquer usuário interno". Hardening 2026-07: caso órfão
    não vaza sub-recursos (PII das partes) a perfis não-gestão — quem destrava
    é a gestão, que pode assumir/reatribuir o caso (ownership.py)."""
    from app.core.database import AsyncSessionLocal
    from app.routers.case_partes import listar_partes

    tok = f"Zzq{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Legado {tok}")
        caso = await _criar_caso(db, cli, f"Caso legado {tok}", resp_id=None)
        await _criar_parte(db, caso, f"Parte Legada {tok}")
        await db.commit()
        try:
            # Gestão continua acessando (sem lockout): pode assumir/reatribuir.
            partes = await listar_partes(caso, db, await _carregar_user(db, socio))
            assert [p["nome"] for p in partes] == [f"Parte Legada {tok}"]
            # Advogado SEM vínculo não acessa caso órfão → 403 (não vaza PII).
            with pytest.raises(HTTPException) as exc:
                await listar_partes(caso, db, await _carregar_user(db, adv))
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[adv, socio], client_ids=[cli])


async def test_db03_criar_parte_cifra_em_repouso_e_busca_por_hmac():
    """Fase A: nova gravação não deixa CPF/e-mail/telefone em plaintext."""
    from starlette.requests import Request
    from app.core.database import AsyncSessionLocal
    from app.routers.case_partes import ParteCreate, criar_parte, listar_partes
    from app.routers.search import busca_global

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, "Cliente DB03 cifrado")
        caso = await _criar_caso(db, cli, "Caso DB03 cifrado", resp_id=uid)
        await db.commit()
        cu = await _carregar_user(db, uid)
        body = ParteCreate(
            tipo="autor", nome="Pessoa Fictícia DB03",
            cpf_cnpj="153.509.460-56",
            email="pessoa@example.test", telefone="(31) 99999-9999",
        )
        try:
            criado = await criar_parte(caso, body, db, cu)
            row = (await db.execute(text(
                "SELECT cpf_cnpj, cpf_cnpj_enc, cpf_cnpj_hash, email, email_enc, "
                "telefone, telefone_enc FROM case_partes WHERE id = :id"
            ), {"id": criado["id"]})).mappings().one()
            assert row["cpf_cnpj"] is None and row["email"] is None and row["telefone"] is None
            assert row["cpf_cnpj_enc"] and row["cpf_cnpj_hash"]
            assert row["email_enc"] and row["telefone_enc"]

            partes = await listar_partes(caso, db, cu)
            assert partes[0]["cpf_cnpj"] == "153.509.460-56"
            assert partes[0]["email"] == "pessoa@example.test"
            assert partes[0]["telefone"] == "(31) 99999-9999"

            req = Request({
                "type": "http", "method": "GET", "path": "/search", "headers": [],
                "query_string": b"", "client": ("127.0.0.1", 50158),
                "server": ("testserver", 80), "scheme": "http",
            })
            busca = await busca_global(
                request=req, q="15350946056", tipo="cpf", limit=6, db=db, cu=cu,
            )
            assert any(r.get("id") == caso for r in busca["resultados"])

            with pytest.raises(HTTPException) as exc:
                await criar_parte(caso, body, db, cu)
            assert exc.value.status_code == 409
        finally:
            await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
            await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
            await _limpar(db, case_ids=[caso], user_ids=[uid], client_ids=[cli])
