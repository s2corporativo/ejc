"""Despesas processuais por caso — Issue #809.

Cobre lançamento, ownership, faturamento em `custas_despesas`, bloqueio de
remoção depois de faturar e acesso do papel financeiro ao ato de faturamento.
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
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
            "INSERT INTO cases "
            "(id, titulo, area, status, client_id, advogado_responsavel_id, proxima_acao) "
            "VALUES (:id, 'Caso Despesa Teste', 'civil', 'em_instrucao', :cid, :resp, 'Revisar')"
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
    if user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
    for user_id in user_ids:
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": user_id})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def test_lancar_e_faturar_gera_fee_custas_despesas():
    from app.core.database import AsyncSessionLocal
    from app.models.case_despesa import CaseDespesa
    from app.models.fee import Fee, FeeTipo
    from app.routers.despesas_processuais import DespesaIn, FaturarIn, faturar, lancar

    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db)
        client_id = await _criar_cliente(db, "Cliente Despesa", advogado)
        case_id = await _criar_caso(db, client_id, advogado)
        await db.commit()
        try:
            user = await _carregar_user(db, advogado)
            r1 = await lancar(
                DespesaIn(
                    case_id=case_id,
                    data=date(2026, 1, 10),
                    valor=Decimal("150.00"),
                    descricao="Cópias autenticadas",
                    categoria="copias",
                ),
                db,
                user,
            )
            r2 = await lancar(
                DespesaIn(
                    case_id=case_id,
                    data=date(2026, 1, 11),
                    valor=Decimal("80.50"),
                    descricao="Diligência ao fórum",
                    categoria="diligencia",
                ),
                db,
                user,
            )
            assert r1["id"] and r2["id"]

            resultado = await faturar(case_id, FaturarIn(), db, user)
            assert resultado["lancamentos"] == 2
            assert Decimal(str(resultado["valor"])) == Decimal("230.50")

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
            assert all(entry.fee_id == fee.id for entry in entradas)
        finally:
            await _limpar(
                db,
                case_ids=[case_id],
                client_ids=[client_id],
                user_ids=[advogado],
            )


async def test_advogado_sem_vinculo_nao_lanca_despesa():
    from app.core.database import AsyncSessionLocal
    from app.routers.despesas_processuais import DespesaIn, lancar

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
                    DespesaIn(
                        case_id=case_id,
                        data=date(2026, 1, 10),
                        valor=Decimal("50.00"),
                        descricao="Tentativa indevida",
                    ),
                    db,
                    user_estranho,
                )
            assert exc.value.status_code == 403
        finally:
            await _limpar(
                db,
                case_ids=[case_id],
                client_ids=[client_id],
                user_ids=[dono, estranho],
            )


async def test_financeiro_pode_faturar_mas_nao_lancar_no_caso():
    from app.core.database import AsyncSessionLocal
    from app.models.fee import FeeTipo
    from app.routers.despesas_processuais import DespesaIn, FaturarIn, faturar, lancar

    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db)
        financeiro = await _criar_user(db, "financeiro")
        client_id = await _criar_cliente(db, "Cliente Financeiro", advogado)
        case_id = await _criar_caso(db, client_id, advogado)
        await db.commit()
        try:
            adv_user = await _carregar_user(db, advogado)
            fin_user = await _carregar_user(db, financeiro)
            await lancar(
                DespesaIn(
                    case_id=case_id,
                    data=date(2026, 2, 1),
                    valor=Decimal("75.00"),
                    descricao="Custas de distribuição",
                    categoria="custas",
                ),
                db,
                adv_user,
            )

            with pytest.raises(HTTPException) as exc:
                await lancar(
                    DespesaIn(
                        case_id=case_id,
                        data=date(2026, 2, 2),
                        valor=Decimal("10.00"),
                        descricao="Lançamento indevido",
                    ),
                    db,
                    fin_user,
                )
            assert exc.value.status_code == 403

            resultado = await faturar(case_id, FaturarIn(), db, fin_user)
            from app.models.fee import Fee
            fee = (
                await db.execute(select(Fee).where(Fee.id == resultado["fee_id"]))
            ).scalar_one()
            assert fee.tipo == FeeTipo.custas_despesas
        finally:
            await _limpar(
                db,
                case_ids=[case_id],
                client_ids=[client_id],
                user_ids=[advogado, financeiro],
            )


async def test_sem_pendencia_e_remover_faturada_retornam_422():
    from app.core.database import AsyncSessionLocal
    from app.routers.despesas_processuais import (
        DespesaIn,
        FaturarIn,
        faturar,
        lancar,
        remover,
    )

    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db)
        client_id = await _criar_cliente(db, "Cliente Sem Pendência", advogado)
        case_id = await _criar_caso(db, client_id, advogado)
        await db.commit()
        try:
            user = await _carregar_user(db, advogado)
            with pytest.raises(HTTPException) as exc:
                await faturar(case_id, FaturarIn(), db, user)
            assert exc.value.status_code == 422

            entry = await lancar(
                DespesaIn(
                    case_id=case_id,
                    data=date(2026, 1, 10),
                    valor=Decimal("100.00"),
                    descricao="Custas iniciais",
                    categoria="custas",
                ),
                db,
                user,
            )
            await faturar(case_id, FaturarIn(), db, user)

            with pytest.raises(HTTPException) as exc:
                await remover(entry["id"], db, user)
            assert exc.value.status_code == 422
        finally:
            await _limpar(
                db,
                case_ids=[case_id],
                client_ids=[client_id],
                user_ids=[advogado],
            )
