"""Reagendar prazo vencido para o futuro devolve o status a 'pendente'.

Auditoria de 22/08/2026 (Issue #1237), achado 29 — §71 prioridade 3 (prazos).

`PATCH /deadlines/{id}` monta as mudanças com `model_dump(exclude_unset=True)`
e aplica só o que veio. `CentralAtividades.tsx` reagenda mandando **só**
`data_prazo`, então o status `vencido` — escrito pelo job das 07:10
(`scheduler._marcar_prazos_vencidos`) — sobrevivia à mudança de data. O prazo
ficava rotulado "vencido" com data futura: aparecia na aba Vencidos sem ter
vencido, e o painel (que conta por DATA, desde a correção do achado 7)
discordava da listagem (que filtra por STATUS) sobre o mesmo prazo.

A correção é a regra inversa do job: ele faz pendente→vencido quando a data
passa; o PATCH faz vencido→pendente quando a data volta para frente. Não
inventa transição nova, fecha a que faltava.

Fronteiras que os testes fixam, porque é onde uma reabertura automática
poderia causar dano:
  - status enviado EXPLICITAMENTE na mesma chamada manda (não é sobrescrito);
  - `concluido` e `cancelado` NUNCA são reabertos por troca de data;
  - reagendar para o PASSADO não reabre (continua vencido, corretamente);
  - hoje conta como não-vencido (o job usa `data_prazo < hoje`), então
    reagendar para hoje reabre — mesma fronteira dos dois lados.

Postgres obrigatório, como nos demais `*_dblevel.py`. Sem RUN_DB_TESTS=1, pula
(o CI define RUN_DB_TESTS=1 no job db-validation).
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.deadline import Deadline
from app.routers.deadlines import atualizar
from app.schemas.deadline import DeadlineUpdate

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)

HOJE = date.today()
FUTURO = HOJE + timedelta(days=10)
PASSADO = HOJE - timedelta(days=10)


async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Prazo Reagendado', :role, true)"),
        {"id": uid, "email": f"reag-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_deadline(db, *, resp_id, data_prazo, status) -> str:
    did = str(uuid4())
    await db.execute(
        text("INSERT INTO deadlines (id, titulo, tipo, prioridade, status, "
             "data_prazo, responsavel_id, confirmado) VALUES "
             "(:id, :titulo, 'processual', 'media', :status, :data_prazo, :resp, true)"),
        {"id": did, "titulo": f"Prazo {did[:8]}", "status": status,
         "data_prazo": data_prazo, "resp": resp_id},
    )
    return did


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _status_no_banco(deadline_id: str) -> str:
    async with AsyncSessionLocal() as db:
        dl = (await db.execute(
            select(Deadline).where(Deadline.id == deadline_id))).scalar_one()
        return getattr(dl.status, "value", dl.status)


async def _contar_audit(db, acao: str, registro_id: str) -> int:
    return (await db.execute(
        text("SELECT count(*) FROM audit_logs WHERE acao = :a AND registro_id = :id"),
        {"a": acao, "id": registro_id},
    )).scalar()


async def _limpar(db, *, deadline_ids=(), user_ids=()):
    for did in deadline_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE registro_id = :id"), {"id": did})
        await db.execute(text("DELETE FROM deadlines WHERE id = :id"), {"id": did})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_reagendar_vencido_para_o_futuro_reabre_como_pendente():
    """O caso do achado: só `data_prazo` no corpo, como a tela manda."""
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db)
        did = await _criar_deadline(db, resp_id=adv, data_prazo=PASSADO,
                                    status="vencido")
        await db.commit()
        try:
            cu = await _carregar_user(db, adv)
            out = await atualizar(did, DeadlineUpdate(data_prazo=FUTURO),
                                  db=db, cu=cu)

            assert out.status == "pendente", (
                "prazo reagendado para o futuro seguiu rotulado como vencido"
            )
            assert await _status_no_banco(did) == "pendente"

            async with AsyncSessionLocal() as db2:
                # A reabertura é registrada — mudança de status feita pelo
                # sistema sem o usuário pedir precisa deixar rastro.
                assert await _contar_audit(db2, "PRAZO_REABERTO", did) == 1
        finally:
            await _limpar(db, deadline_ids=[did], user_ids=[adv])


async def test_reagendar_para_hoje_tambem_reabre():
    """Fronteira: o job usa `data_prazo < hoje`, então hoje não é vencido."""
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db)
        did = await _criar_deadline(db, resp_id=adv, data_prazo=PASSADO,
                                    status="vencido")
        await db.commit()
        try:
            out = await atualizar(did, DeadlineUpdate(data_prazo=HOJE),
                                  db=db, cu=await _carregar_user(db, adv))
            assert out.status == "pendente"
        finally:
            await _limpar(db, deadline_ids=[did], user_ids=[adv])


async def test_reagendar_para_o_passado_nao_reabre():
    """Continua vencido — mudou a data, não deixou de ter vencido."""
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db)
        did = await _criar_deadline(db, resp_id=adv, data_prazo=PASSADO,
                                    status="vencido")
        await db.commit()
        try:
            out = await atualizar(
                did, DeadlineUpdate(data_prazo=HOJE - timedelta(days=3)),
                db=db, cu=await _carregar_user(db, adv))
            assert out.status == "vencido"
            async with AsyncSessionLocal() as db2:
                assert await _contar_audit(db2, "PRAZO_REABERTO", did) == 0
        finally:
            await _limpar(db, deadline_ids=[did], user_ids=[adv])


@pytest.mark.parametrize("status_final", ["concluido", "cancelado"])
async def test_concluido_e_cancelado_nunca_sao_reabertos_por_troca_de_data(
    status_final,
):
    """Trocar a data de um prazo encerrado não pode ressuscitá-lo."""
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db)
        did = await _criar_deadline(db, resp_id=adv, data_prazo=PASSADO,
                                    status=status_final)
        await db.commit()
        try:
            out = await atualizar(did, DeadlineUpdate(data_prazo=FUTURO),
                                  db=db, cu=await _carregar_user(db, adv))
            assert out.status == status_final
        finally:
            await _limpar(db, deadline_ids=[did], user_ids=[adv])


async def test_status_explicito_na_mesma_chamada_tem_precedencia():
    """Quem manda status junto com a data está dizendo o que quer."""
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db)
        did = await _criar_deadline(db, resp_id=adv, data_prazo=PASSADO,
                                    status="vencido")
        await db.commit()
        try:
            out = await atualizar(
                did, DeadlineUpdate(data_prazo=FUTURO, status="vencido"),
                db=db, cu=await _carregar_user(db, adv))
            assert out.status == "vencido", (
                "status explícito no payload foi sobrescrito pela reabertura"
            )
            async with AsyncSessionLocal() as db2:
                assert await _contar_audit(db2, "PRAZO_REABERTO", did) == 0
        finally:
            await _limpar(db, deadline_ids=[did], user_ids=[adv])
