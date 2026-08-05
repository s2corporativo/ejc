"""Prazos vencidos + trilha de conclusão (auditoria pré-produção).

Contrato coberto:
  - `_marcar_prazos_vencidos` (scheduler): prazo PENDENTE com data_prazo < hoje
    vira status='vencido' e gera UMA notificação 'prazo' ao responsável.
    Idempotente: 2ª execução não re-alerta (transição pendente→vencido é a
    guarda). Prazo concluído já vencido NÃO é tocado.
  - PATCH /deadlines/{id} status→concluido (atualizar): seta concluido_por +
    data_conclusao e grava AuditLog PRAZO_CONCLUIDO; re-patch não duplica.

Postgres OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: handler/job direto
com `AsyncSessionLocal`). Sem RUN_DB_TESTS=1, pula.

NOTA: `concluido_por` é adicionada por migration (agente db-migrations); o teste
de conclusão só passa com a migration aplicada.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.models.deadline import Deadline

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


# ── Helpers (SQL cru, como nos demais *_dblevel.py) ──────────────────────────

async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Prazo Teste', :role, true)"),
        {"id": uid, "email": f"vnc-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_deadline(db, *, resp_id, data_prazo, status="pendente", titulo=None) -> str:
    did = str(uuid4())
    await db.execute(
        text("INSERT INTO deadlines (id, titulo, tipo, prioridade, status, "
             "data_prazo, responsavel_id, confirmado) VALUES "
             "(:id, :titulo, 'processual', 'media', :status, :data_prazo, :resp, true)"),
        {"id": did, "titulo": titulo or f"Prazo {did[:8]}", "status": status,
         "data_prazo": data_prazo, "resp": resp_id},
    )
    return did


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _contar_audit(db, acao: str, registro_id: str) -> int:
    return (await db.execute(
        text("SELECT count(*) FROM audit_logs WHERE acao = :a AND registro_id = :id"),
        {"a": acao, "id": registro_id},
    )).scalar()


async def _contar_notif(db, user_id: str, tipo: str = "prazo") -> int:
    return (await db.execute(
        text("SELECT count(*) FROM notifications WHERE user_id = :u AND tipo = :t"),
        {"u": user_id, "t": tipo},
    )).scalar()


async def _limpar(db, *, deadline_ids=(), user_ids=()):
    for did in deadline_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE registro_id = :id"), {"id": did})
        await db.execute(text("DELETE FROM deadlines WHERE id = :id"), {"id": did})
    for uid in user_ids:
        await db.execute(text("DELETE FROM notifications WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


# ── Testes ────────────────────────────────────────────────────────────────────

async def test_marcar_prazos_vencidos_transiciona_e_alerta_uma_vez():
    from app.core.database import AsyncSessionLocal
    from app.services.scheduler import _marcar_prazos_vencidos

    ontem = date.today() - timedelta(days=1)
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        venc_id = await _criar_deadline(db, resp_id=adv, data_prazo=ontem, status="pendente")
        # Concluído já vencido: NÃO deve ser tocado nem alertado.
        concl_id = await _criar_deadline(db, resp_id=adv, data_prazo=ontem, status="concluido")
        await db.commit()
        try:
            await _marcar_prazos_vencidos()
            async with AsyncSessionLocal() as db2:
                v = (await db2.execute(
                    select(Deadline).where(Deadline.id == venc_id))).scalar_one()
                c = (await db2.execute(
                    select(Deadline).where(Deadline.id == concl_id))).scalar_one()
                assert v.status.value == "vencido"
                assert c.status.value == "concluido"      # intocado
                assert await _contar_notif(db2, adv) == 1  # UM alerta

            # 2ª execução: idempotente — já é 'vencido', não re-alerta.
            await _marcar_prazos_vencidos()
            async with AsyncSessionLocal() as db3:
                assert await _contar_notif(db3, adv) == 1
        finally:
            await _limpar(db, deadline_ids=[venc_id, concl_id], user_ids=[adv])


async def test_marcar_prazos_vencidos_ignora_prazo_do_dia():
    """data_prazo == hoje ainda não venceu (só < hoje)."""
    from app.core.database import AsyncSessionLocal
    from app.services.scheduler import _marcar_prazos_vencidos

    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        hoje_id = await _criar_deadline(db, resp_id=adv, data_prazo=date.today())
        await db.commit()
        try:
            await _marcar_prazos_vencidos()
            async with AsyncSessionLocal() as db2:
                d = (await db2.execute(
                    select(Deadline).where(Deadline.id == hoje_id))).scalar_one()
                assert d.status.value == "pendente"
                assert await _contar_notif(db2, adv) == 0
        finally:
            await _limpar(db, deadline_ids=[hoje_id], user_ids=[adv])


async def test_atualizar_concluido_seta_autor_e_grava_audit():
    from app.core.database import AsyncSessionLocal
    from app.routers.deadlines import atualizar
    from app.schemas.deadline import DeadlineUpdate

    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        did = await _criar_deadline(db, resp_id=adv, data_prazo=date.today())
        await db.commit()
        try:
            cu = await _carregar_user(db, adv)
            out = await atualizar(did, DeadlineUpdate(status="concluido"), db=db, cu=cu)
            assert out.status == "concluido"

            async with AsyncSessionLocal() as db2:
                dl = (await db2.execute(
                    select(Deadline).where(Deadline.id == did))).scalar_one()
                assert dl.status.value == "concluido"
                assert dl.concluido_por == adv
                assert dl.data_conclusao is not None
                assert await _contar_audit(db2, "PRAZO_CONCLUIDO", did) == 1

            # Re-patch idempotente: não duplica audit.
            await atualizar(did, DeadlineUpdate(status="concluido"), db=db,
                            cu=await _carregar_user(db, adv))
            async with AsyncSessionLocal() as db3:
                assert await _contar_audit(db3, "PRAZO_CONCLUIDO", did) == 1
        finally:
            await _limpar(db, deadline_ids=[did], user_ids=[adv])
