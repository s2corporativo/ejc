"""POST /cases/{case_id}/aplicar-extracao — dry_run (preview) vs apply real.

Gap B do #83 (backend). Contrato:
  - dry_run=True  → devolve o que SERIA aplicado, mas NÃO persiste nada
    (nenhuma CaseParte/CasoArea criada) e NÃO grava AuditLog.
  - dry_run=False → aplica e persiste como hoje; grava AuditLog IMPORT_EXTRACAO.
  - Ownership: advogado sem vínculo com o caso → 404 (via _filtro_visibilidade).

Postgres é OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: chama o handler
direto com `AsyncSessionLocal`). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from starlette.background import BackgroundTasks

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


# ── Helpers de fixture (SQL cru, como nos demais *_dblevel.py) ───────────────

async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Extracao Teste', :role, true)"),
        {"id": uid, "email": f"extr-{uid[:8]}@teste.local", "role": role},
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


async def _criar_caso(db, client_id: str, titulo: str, resp_id: str | None) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "advogado_responsavel_id) VALUES "
             "(:id, :titulo, 'civil', 'ativo', :cid, :resp)"),
        {"id": case_id, "titulo": titulo, "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _contar_partes(db, case_id: str) -> int:
    return (await db.execute(
        text("SELECT count(*) FROM case_partes WHERE case_id = :id"), {"id": case_id}
    )).scalar()


async def _contar_areas(db, case_id: str) -> int:
    return (await db.execute(
        text("SELECT count(*) FROM caso_areas WHERE case_id = :id"), {"id": case_id}
    )).scalar()


async def _contar_audit(db, case_id: str) -> int:
    return (await db.execute(
        text("SELECT count(*) FROM audit_logs WHERE acao = 'IMPORT_EXTRACAO' "
             "AND entidade = 'cases' AND registro_id = :id"),
        {"id": case_id},
    )).scalar()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM audit_logs WHERE registro_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM case_movimentos WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM caso_areas WHERE case_id = :id"), {"id": cid})
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


def _payload_req(dry_run: bool = False):
    from app.routers.cases import AplicarExtracaoReq
    return AplicarExtracaoReq(
        identificacao_processual={
            "numero_processo": "1234567-89.2026.8.13.0027",
            "tribunal": "TJMG", "comarca": "Betim", "vara": "2a Vara Civel",
        },
        partes={"autor": "Fulano de Tal", "reu": "Empresa XPTO Ltda",
                "advogados": ["Dra. Ciclana OAB/MG 111"]},
        classificacao={"area": "civel"},
        dry_run=dry_run,
    )


# ── Testes ────────────────────────────────────────────────────────────────────

async def test_dry_run_nao_persiste_e_devolve_preview():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import aplicar_extracao

    tok = f"Dry{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=adv)
        await db.commit()
        try:
            bg = BackgroundTasks()
            resp = await aplicar_extracao(
                caso, _payload_req(dry_run=True), bg,
                dry_run=False, db=db, cu=await _carregar_user(db, adv),
            )
            # Contrato da resposta (preview).
            assert resp["dry_run"] is True
            assert resp["aplicado"] is False
            # FLX-045: preview NÃO re-agenda triagem (nada foi aplicado).
            assert bg.tasks == []
            assert resp["partes_criadas"] == 3   # autor + reu + 1 advogado
            assert resp["areas_criadas"] == 1
            assert resp["campos_preenchidos"] == [
                "numero_processo", "tribunal", "comarca", "vara"]

            # Banco NÃO mudou.
            async with AsyncSessionLocal() as db2:
                assert await _contar_partes(db2, caso) == 0
                assert await _contar_areas(db2, caso) == 0
                assert await _contar_audit(db2, caso) == 0
                # Campos do caso permanecem vazios.
                num = (await db2.execute(
                    text("SELECT numero_processo FROM cases WHERE id = :id"),
                    {"id": caso})).scalar()
                assert num is None
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[adv], client_ids=[cli])


async def test_dry_run_via_query_param():
    """dry_run pode vir pelo query param (payload.dry_run=False, dry_run=True)."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import aplicar_extracao

    tok = f"Qry{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=adv)
        await db.commit()
        try:
            resp = await aplicar_extracao(
                caso, _payload_req(dry_run=False), BackgroundTasks(),
                dry_run=True, db=db, cu=await _carregar_user(db, adv),
            )
            assert resp["dry_run"] is True and resp["aplicado"] is False
            async with AsyncSessionLocal() as db2:
                assert await _contar_partes(db2, caso) == 0
                assert await _contar_audit(db2, caso) == 0
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[adv], client_ids=[cli])


async def test_apply_real_persiste_e_grava_audit():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import aplicar_extracao

    tok = f"App{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=adv)
        await db.commit()
        try:
            bg = BackgroundTasks()
            resp = await aplicar_extracao(
                caso, _payload_req(dry_run=False), bg,
                dry_run=False, db=db, cu=await _carregar_user(db, adv),
            )
            assert resp["dry_run"] is False
            assert resp["aplicado"] is True
            # FLX-045: apply real re-agenda a triagem sobre os dados aplicados
            # (idempotente: só preenche campos vazios).
            from app.services.case_intel import triagem_caso
            assert triagem_caso in [t.func for t in bg.tasks]
            assert resp["partes_criadas"] == 3
            assert resp["areas_criadas"] == 1

            async with AsyncSessionLocal() as db2:
                assert await _contar_partes(db2, caso) == 3
                assert await _contar_areas(db2, caso) == 1
                assert await _contar_audit(db2, caso) == 1
                num = (await db2.execute(
                    text("SELECT numero_processo FROM cases WHERE id = :id"),
                    {"id": caso})).scalar()
                assert num is not None
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[adv], client_ids=[cli])


async def test_ownership_advogado_sem_vinculo_404():
    """Advogado sem vínculo com o caso → 404 (não vaza, não aplica).
    Vale tanto para dry_run quanto para apply real."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import aplicar_extracao

    tok = f"Own{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        resp_adv = await _criar_user(db, "advogado")
        outro_adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=resp_adv)
        await db.commit()
        try:
            outro = await _carregar_user(db, outro_adv)
            for dr in (True, False):
                with pytest.raises(HTTPException) as exc:
                    await aplicar_extracao(
                        caso, _payload_req(dry_run=dr), BackgroundTasks(),
                        dry_run=dr, db=db, cu=outro,
                    )
                assert exc.value.status_code == 404
            # Nada foi criado por nenhuma das tentativas.
            async with AsyncSessionLocal() as db2:
                assert await _contar_partes(db2, caso) == 0
                assert await _contar_audit(db2, caso) == 0
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv], client_ids=[cli])
