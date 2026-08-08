"""Despesas processuais por caso (F3.2 / Issue #806).

Mesmo desenho de timesheet.py: lançamento cru (qualquer um com acesso ao
caso) + consolidação explícita em Fee (custas_despesas), restrita a
advogado/gestão/financeiro. Cobre:
  (a) lançar grava despesa vinculada ao caso;
  (b) advogado SEM vínculo com o caso (nem responsável, nem auxiliar) não lança;
  (c) faturar consolida as pendentes em UM Fee custas_despesas e marca fee_id;
  (d) faturar sem despesa pendente → 422;
  (e) remover despesa já faturada → 422 (não pode apagar o que já virou honorário).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Despesa Teste', :role, true)"
        ),
        {"id": uid, "email": f"despesa-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _carregar_user(db, user_id: str):
    from app.models.user import User

    return (await db.execute(select(User).where(User.id == user_id))).scalar_one()


async def _criar_cliente(db, nome: str, responsavel_id: str) -> str:
    client_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO clients (id, tipo, nome, status, responsavel_id) "
            "VALUES (:id, 'PF', :nome, 'ativo', :resp)"
        ),
        {"id": client_id, "nome": nome, "resp": responsavel_id},
    )
    return client_id


async def _criar_caso(db, client_id: str, responsavel_id: str) -> str:
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id, advogado_responsavel_id) "
            "VALUES (:id, 'Caso Despesa Teste', 'civil', 'em_instrucao', :cid, :resp)"
        ),
        {"id": case_id, "cid": client_id, "resp": responsavel_id},
    )
    return case_id


async def _limpar(db, *, case_ids=(), client_ids=(), user_ids=()):
    for case_id in case_ids:
        await db.execute(
            text("DELETE FROM case_despesas WHERE case_id = :id"), {"id": case_id}
        )
        await db.execute(text("DELETE FROM fees WHERE case_id = :id"), {"id": case_id})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": case_id})
    for client_id in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    for user_id in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": user_id})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def test_lancar_despesa_e_faturar_gera_fee_custas_despesas():
    from app.core.database import AsyncSessionLocal
    from app.models.case_despesa import CaseDespesa
    from app.models.fee import Fee, FeeTipo
    from app.routers.despesas_processuais import DespesaIn, FaturarIn, faturar, lancar

    case_id = None
    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db)
        client_id = await _criar_cliente(db, "Cliente Despesa", advogado)
        case_id = await _criar_caso(db, client_id, advogado)
        await db.commit()
        try:
            user = await _carregar_user(db, advogado)
            r1 = await lancar(
                DespesaIn(case_id=case_id, data="2026-01-10", valor=150.0,
                          descricao="Cópias autenticadas", categoria="copias"),
                db, user,
            )
            r2 = await lancar(
                DespesaIn(case_id=case_id, data="2026-01-11", valor=80.5,
                          descricao="Diligência ao fórum", categoria="diligencia"),
                db, user,
            )
            assert r1["id"] and r2["id"]

            resultado = await faturar(case_id, FaturarIn(), db, user)
            assert resultado["lancamentos"] == 2
            assert float(resultado["valor"]) == pytest.approx(230.5)

            fee = (
                await db.execute(select(Fee).where(Fee.id == resultado["fee_id"]))
            ).scalar_one()
            assert fee.tipo == FeeTipo.custas_despesas
            assert fee.case_id == case_id
            assert fee.client_id == client_id

            entradas = (
                await db.execute(
                    select(CaseDespesa).where(CaseDespesa.case_id == case_id)
                )
            ).scalars().all()
            assert all(e.fee_id == fee.id for e in entradas)
        finally:
            await _limpar(db, case_ids=[case_id], client_ids=[client_id], user_ids=[advogado])


async def test_advogado_sem_vinculo_nao_lanca_despesa():
    from app.core.database import AsyncSessionLocal
    from app.routers.despesas_processuais import DespesaIn, lancar

    case_id = None
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db)
        estranho = await _criar_user(db)
        client_id = await _criar_cliente(db, "Cliente Alheio", dono)
        case_id = await _criar_caso(db, client_id, dono)
        await db.commit()
        try:
            user_estranho = await _carregar_user(db, estranho)
            with pytest.raises(HTTPException) as exc:
                await lancar(
                    DespesaIn(case_id=case_id, data="2026-01-10", valor=50.0,
                              descricao="Tentativa indevida"),
                    db, user_estranho,
                )
            assert exc.value.status_code == 403
        finally:
            await _limpar(
                db, case_ids=[case_id], client_ids=[client_id], user_ids=[dono, estranho]
            )


async def test_faturar_sem_pendencia_e_remover_faturada_dao_422():
    from app.core.database import AsyncSessionLocal
    from app.routers.despesas_processuais import DespesaIn, FaturarIn, faturar, lancar, remover

    case_id = None
    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db)
        client_id = await _criar_cliente(db, "Cliente Sem Pendencia", advogado)
        case_id = await _criar_caso(db, client_id, advogado)
        await db.commit()
        try:
            user = await _carregar_user(db, advogado)

            with pytest.raises(HTTPException) as exc:
                await faturar(case_id, FaturarIn(), db, user)
            assert exc.value.status_code == 422

            r = await lancar(
                DespesaIn(case_id=case_id, data="2026-01-10", valor=100.0,
                          descricao="Custas iniciais", categoria="custas"),
                db, user,
            )
            await faturar(case_id, FaturarIn(), db, user)

            with pytest.raises(HTTPException) as exc:
                await remover(r["id"], db, user)
            assert exc.value.status_code == 422
        finally:
            await _limpar(db, case_ids=[case_id], client_ids=[client_id], user_ids=[advogado])
