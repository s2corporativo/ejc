"""Rotas de /api/saneamento/* contra Postgres real (migration 154 aplicada).

Contrato coberto:
  - RBAC: `advogado_auxiliar` lê, mas não decide nem aplica dedup — só
    `advogado`/`socio`/`admin`/`superadmin` (regra inegociável: sinaliza,
    quem decide é sempre um advogado, nunca um job/estagiário).
  - `POST /indicativos/{id}/decidir`: grava decisao+decidido_por+decidido_em
    e recusa decidir de novo o mesmo indicativo (409).
  - `POST /duplicatas/{id}/aplicar`: recusa aplicar `multi_grau`/
    `conexo_sugerido` (essas nunca são fundidas) e exige `confirmar=true`.
  - `GET /tpu/cobertura`: reflete a semente da migration (código 246).

O `AuthMiddleware` global do EJC decodifica o JWT ele mesmo, ANTES da injeção
de dependências — `dependency_overrides[get_current_user]` não o atravessa
(diferente de chamar o handler do router direto, como os *_dblevel.py de
agenda_eventos fazem). Por isso cada teste usa um Bearer token real, gerado
com o mesmo `create_access_token` que o login produz, sobre um usuário
efetivamente inserido em `users` (FK de audit_logs.user_id exige linha real).

Sem RUN_DB_TESTS=1, pula (mesmo padrão dos demais *_dblevel.py).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

_pg = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)

NUM_CNJ_OFICIAL = "00008323520184013202"
API = "/api/saneamento"


async def _criar_user(db, role: str) -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Saneamento Teste', :role, true)"),
        {"id": uid, "email": f"san-{uid[:8]}@teste.local", "role": role},
    )
    await db.commit()
    return uid


def _token_para(uid: str, role: str) -> dict[str, str]:
    from app.core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token(uid, role)}"}


async def _limpar(db):
    """Limpa só as tabelas do módulo. `audit_logs` é WORM (Issue #582) — não
    apagável por teste — e `users` referenciado por FK de audit_logs criado
    nesta rodada; deixar as linhas de teste (usuário/log) no banco descartável
    local é inofensivo e evita violar a imutabilidade ou a FK."""
    await db.execute(text("DELETE FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
                      {"n": NUM_CNJ_OFICIAL})
    await db.execute(text("DELETE FROM saneamento_plano_dedup WHERE numero_cnj = :n"),
                      {"n": NUM_CNJ_OFICIAL})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


def _client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@_pg
async def test_leitor_nao_pode_decidir_indicativo():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado_auxiliar")
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, true, 'alta')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        ind_id = (await db.execute(
            text("SELECT id FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    try:
        resp = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "teste"},
            headers=_token_para(uid, "advogado_auxiliar"),
        )
        assert resp.status_code == 403
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db)


@_pg
async def test_advogado_decide_e_segunda_decisao_e_recusada():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado")
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, true, 'alta')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        ind_id = (await db.execute(
            text("SELECT id FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    headers = _token_para(uid, "advogado")
    try:
        resp1 = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "silêncio de 400 dias"},
            headers=headers,
        )
        assert resp1.status_code == 200, resp1.text
        body = resp1.json()
        assert body["decisao"] == "encerrar"
        assert body["decidido_por"] == uid

        resp2 = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "manter_ativo", "justificativa": "segunda tentativa"},
            headers=headers,
        )
        assert resp2.status_code == 409
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db)


@_pg
async def test_aplicar_dedup_recusa_multi_grau_e_exige_confirmacao():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado")
        await db.execute(
            text("INSERT INTO saneamento_plano_dedup "
                 "(numero_cnj, id_interno_principal, ids_absorvidos, tipo) "
                 "VALUES (:n, 'p1', ARRAY['p2'], 'multi_grau')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        plano_id = (await db.execute(
            text("SELECT id FROM saneamento_plano_dedup WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    headers = _token_para(uid, "advogado")
    try:
        sem_confirmar = _client().post(
            f"{API}/duplicatas/{plano_id}/aplicar", json={"confirmar": False}, headers=headers,
        )
        assert sem_confirmar.status_code == 422

        multi_grau = _client().post(
            f"{API}/duplicatas/{plano_id}/aplicar", json={"confirmar": True}, headers=headers,
        )
        assert multi_grau.status_code == 422
        assert "multi_grau" in multi_grau.text or "nunca" in multi_grau.text
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db)


@_pg
async def test_cobertura_tpu_reflete_semente_da_migration():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado_auxiliar")

    try:
        resp = _client().get(f"{API}/tpu/cobertura", headers=_token_para(uid, "advogado_auxiliar"))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 1
        assert body["classificados"] >= 1  # código 246, semeado pela migration
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db)
