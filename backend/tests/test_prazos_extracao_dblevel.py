"""Gap C (#83) — prazos extraídos por IA materializados como RASCUNHO.

Contrato coberto:
  - aplicar_extracao materializa `payload.prazos` em Deadline com
    confirmado=false, origem='importacao_ia', origem_documento_id setado,
    status=pendente; conta `prazos_criados`.
  - Prazo sem data fatal parseável → NÃO cria Deadline (nunca inventa).
  - Dedup: 2ª aplicação idêntica não duplica.
  - dry_run=true → conta prazos_criados mas NÃO persiste (0 Deadline no banco).
  - PATCH /deadlines/{id}/confirmar → confirmado=true + AuditLog PRAZO_CONFIRMADO;
    ownership (advogado sem vínculo → 403/404).

Postgres OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: handler direto com
`AsyncSessionLocal`). Sem RUN_DB_TESTS=1, pula.
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
             "VALUES (:id, :email, 'x', 'Prazo Teste', :role, true)"),
        {"id": uid, "email": f"prz-{uid[:8]}@teste.local", "role": role},
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
             "(:id, :titulo, 'civil', 'em_instrucao', :cid, :resp)"),
        {"id": case_id, "titulo": titulo, "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _criar_documento(db, case_id: str) -> str:
    """Documento mínimo p/ FK origem_documento_id (nullable, mas testamos com valor)."""
    did = str(uuid4())
    await db.execute(
        text("INSERT INTO documents (id, titulo, filename, filepath, tipo, case_id) "
             "VALUES (:id, 'Petição', 'peticao.pdf', '/tmp/x.pdf', 'peticao', :cid)"),
        {"id": did, "cid": case_id},
    )
    return did


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _deadlines_do_caso(db, case_id: str):
    from app.models.deadline import Deadline
    return (await db.execute(
        select(Deadline).where(Deadline.case_id == case_id,
                               Deadline.deleted_at.is_(None))
    )).scalars().all()


async def _contar_audit(db, acao: str, registro_id: str) -> int:
    return (await db.execute(
        text("SELECT count(*) FROM audit_logs WHERE acao = :a AND registro_id = :id"),
        {"a": acao, "id": registro_id},
    )).scalar()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM audit_logs WHERE registro_id = :id"), {"id": cid})
        # Audit de prazos (registro_id = id do deadline) ANTES de apagar deadlines.
        await db.execute(text("DELETE FROM audit_logs WHERE registro_id IN "
                              "(SELECT id FROM deadlines WHERE case_id = :id)"), {"id": cid})
        await db.execute(text("DELETE FROM deadlines WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM case_movimentos WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM caso_areas WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM case_partes WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM documents WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


def _payload_prazos(prazos, doc_id=None, dry_run=False):
    from app.routers.cases import AplicarExtracaoReq
    return AplicarExtracaoReq(prazos=prazos, origem_documento_id=doc_id, dry_run=dry_run)


# ── Testes ────────────────────────────────────────────────────────────────────

async def test_apply_cria_deadline_rascunho_com_rastreabilidade():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import aplicar_extracao

    tok = f"Prz{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=adv)
        doc = await _criar_documento(db, caso)
        await db.commit()
        try:
            prazos = [
                {"tipo": "contestação", "termo_final": "10/07/2026",
                 "fatal": True, "base_legal": "CPC art. 335"},
                {"tipo": "recurso", "termo_final": None},          # sem data → ignora
                {"tipo": "audiência", "termo_final": "sem data"},  # não parseável → ignora
            ]
            resp = await aplicar_extracao(
                caso, _payload_prazos(prazos, doc_id=doc), BackgroundTasks(),
                dry_run=False, db=db, cu=await _carregar_user(db, adv),
            )
            assert resp["aplicado"] is True
            assert resp["prazos_criados"] == 1   # só o que tem data fatal válida

            async with AsyncSessionLocal() as db2:
                dls = await _deadlines_do_caso(db2, caso)
                assert len(dls) == 1
                d = dls[0]
                assert d.confirmado is False
                assert d.origem == "importacao_ia"
                assert d.origem_documento_id == doc
                assert d.status.value == "pendente"
                assert d.tipo.value == "processual"
                assert d.data_prazo.isoformat() == "2026-07-10"
                assert d.responsavel_id == adv
                assert d.base_legal == "CPC art. 335"
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[adv], client_ids=[cli])


async def test_dedup_nao_duplica_na_segunda_chamada():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import aplicar_extracao

    tok = f"Ded{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=adv)
        await db.commit()
        try:
            prazos = [{"tipo": "contestação", "termo_final": "2026-07-10"}]
            r1 = await aplicar_extracao(
                caso, _payload_prazos(prazos), BackgroundTasks(),
                dry_run=False, db=db, cu=await _carregar_user(db, adv),
            )
            assert r1["prazos_criados"] == 1
            r2 = await aplicar_extracao(
                caso, _payload_prazos(prazos), BackgroundTasks(),
                dry_run=False, db=db, cu=await _carregar_user(db, adv),
            )
            assert r2["prazos_criados"] == 0   # dedup (mesma data_prazo+titulo)

            async with AsyncSessionLocal() as db2:
                assert len(await _deadlines_do_caso(db2, caso)) == 1
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[adv], client_ids=[cli])


async def test_dry_run_conta_mas_nao_persiste():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import aplicar_extracao

    tok = f"Dry{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=adv)
        await db.commit()
        try:
            prazos = [{"tipo": "contestação", "termo_final": "10/07/2026"}]
            resp = await aplicar_extracao(
                caso, _payload_prazos(prazos, dry_run=True), BackgroundTasks(),
                dry_run=False, db=db, cu=await _carregar_user(db, adv),
            )
            assert resp["dry_run"] is True
            assert resp["prazos_criados"] == 1   # conta na prévia

            async with AsyncSessionLocal() as db2:
                assert len(await _deadlines_do_caso(db2, caso)) == 0  # nada persistido
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[adv], client_ids=[cli])


async def test_confirmar_seta_confirmado_e_grava_audit():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import aplicar_extracao
    from app.routers.deadlines import confirmar

    tok = f"Cnf{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=adv)
        await db.commit()
        try:
            await aplicar_extracao(
                caso, _payload_prazos([{"tipo": "contestação", "termo_final": "10/07/2026"}]),
                BackgroundTasks(), dry_run=False, db=db,
                cu=await _carregar_user(db, adv),
            )
            dls = await _deadlines_do_caso(db, caso)
            did = dls[0].id

            out = await confirmar(did, db=db, cu=await _carregar_user(db, adv))
            assert out.confirmado is True

            async with AsyncSessionLocal() as db2:
                dl = (await _deadlines_do_caso(db2, caso))[0]
                assert dl.confirmado is True
                assert await _contar_audit(db2, "PRAZO_CONFIRMADO", did) == 1
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[adv], client_ids=[cli])


async def test_confirmar_ownership_sem_vinculo_bloqueia():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import aplicar_extracao
    from app.routers.deadlines import confirmar

    tok = f"Own{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        resp_adv = await _criar_user(db, "advogado")
        outro_adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=resp_adv)
        await db.commit()
        try:
            await aplicar_extracao(
                caso, _payload_prazos([{"tipo": "contestação", "termo_final": "10/07/2026"}]),
                BackgroundTasks(), dry_run=False, db=db,
                cu=await _carregar_user(db, resp_adv),
            )
            did = (await _deadlines_do_caso(db, caso))[0].id

            with pytest.raises(HTTPException) as exc:
                await confirmar(did, db=db, cu=await _carregar_user(db, outro_adv))
            assert exc.value.status_code in (403, 404)

            async with AsyncSessionLocal() as db2:
                dl = (await _deadlines_do_caso(db2, caso))[0]
                assert dl.confirmado is False  # continua rascunho
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[resp_adv, outro_adv], client_ids=[cli])
