"""Despesa processual reembolsável entra como saída nos números financeiros.

Defeito (plano ERP/agenda/IA, achado E2): o reembolso do cliente (fee
`custas_despesas` pago) entrava como receita no resultado do escritório — base
do "disponível para distribuição" — mas o adiantamento (`case_despesas`) nunca
era descontado. O reembolso aparecia como lucro. O mesmo valia para o snapshot
de fechamento, a rentabilidade por caso e o extrato do caso; o relatório do
cliente previa `reembolsos`, mas nenhuma fonte o alimentava.

Usa a competência 2099-03 para não somar dados de outros testes.
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL com migrations (defina RUN_DB_TESTS=1)",
)

COMPETENCIA = "2099-03"


async def _user(db, role: str) -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Reembolso Teste', :role, true)"),
        {"id": uid, "email": f"reemb-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _carregar_user(db, uid: str):
    from app.models.user import User

    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _cenario(db):
    adv = await _user(db, "advogado")
    fin = await _user(db, "financeiro")
    client_id = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, status, responsavel_id) "
             "VALUES (:id, 'PF', 'Cliente Reembolso', 'ativo', :resp)"),
        {"id": client_id, "resp": adv},
    )
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, advogado_responsavel_id) "
             "VALUES (:id, 'Caso Reembolso', 'civil', 'em_instrucao', :cid, :resp)"),
        {"id": case_id, "cid": client_id, "resp": adv},
    )
    fee_id = str(uuid4())
    await db.execute(
        text("INSERT INTO fees (id, tipo, status, descricao, valor, case_id, client_id, data_pagamento) "
             "VALUES (:id, 'custas_despesas', 'pago', 'Reembolso de custas', 250.00, :case, :cli, :d)"),
        {"id": fee_id, "case": case_id, "cli": client_id, "d": date(2099, 3, 20)},
    )
    await db.execute(
        text("INSERT INTO fee_payments (id, fee_id, valor, data_pagamento) "
             "VALUES (:id, :fee, 250.00, :d)"),
        {"id": str(uuid4()), "fee": fee_id, "d": date(2099, 3, 20)},
    )
    await db.execute(
        text("INSERT INTO case_despesas (id, case_id, user_id, data, valor, descricao, categoria, fee_id) "
             "VALUES (:id, :case, :uid, :d, 250.00, 'Custas iniciais', 'custas', :fee)"),
        {"id": str(uuid4()), "case": case_id, "uid": adv, "d": date(2099, 3, 5), "fee": fee_id},
    )
    await db.commit()
    return adv, fin, client_id, case_id


@pytest.mark.asyncio
async def test_reembolso_nao_vira_lucro_nos_numeros_financeiros():
    async with AsyncSessionLocal() as db:
        adv, fin, client_id, case_id = await _cenario(db)
        try:
            await _verificar(db, adv, fin, client_id, case_id)
        finally:
            await _limpar(db, adv, fin, client_id, case_id)


async def _limpar(db, adv, fin, client_id, case_id):
    await db.rollback()
    await db.execute(text("DELETE FROM case_despesas WHERE case_id=:c"), {"c": case_id})
    await db.execute(
        text("DELETE FROM fee_payments WHERE fee_id IN (SELECT id FROM fees WHERE case_id=:c)"),
        {"c": case_id},
    )
    await db.execute(text("DELETE FROM fees WHERE case_id=:c"), {"c": case_id})
    await db.execute(text("DELETE FROM cases WHERE id=:c"), {"c": case_id})
    await db.execute(text("DELETE FROM clients WHERE id=:c"), {"c": client_id})
    await db.execute(text("DELETE FROM users WHERE id IN (:a, :f)"), {"a": adv, "f": fin})
    await db.commit()


async def _verificar(db, adv, fin, client_id, case_id):
    from app.routers.extratos import extrato_caso
    from app.routers.financeiro.governanca import rentabilidade_financeira
    from app.routers.relatorio_cliente import relatorio_financeiro_cliente
    from app.services.finance_governance import resultado_escritorio_competencia

    # Resultado do escritório (base da distribuição aos sócios): o
    # reembolso de 250 e o adiantamento de 250 se anulam.
    assert await resultado_escritorio_competencia(db, COMPETENCIA) == Decimal("0.00")

    # Rentabilidade por caso.
    rent = await rentabilidade_financeira(
        competencia=COMPETENCIA, db=db, cu=await _carregar_user(db, fin)
    )
    linhas = [c for c in rent["casos"] if c["case_id"] == case_id]
    assert linhas and float(linhas[0]["despesas"]) == 250.0
    assert float(linhas[0]["resultado"]) == 0.0

    # Extrato do caso.
    extrato = await extrato_caso(case_id, db=db, cu=await _carregar_user(db, adv))
    assert extrato["resumo"]["saidas"] == 250.0
    assert extrato["resumo"]["saldo"] == 0.0
    assert any(c.get("reembolsavel") for c in extrato["custos"])

    # Relatório financeiro do cliente: `reembolsos` deixa de ser sempre 0.
    rel = await relatorio_financeiro_cliente(
        client_id, db=db, cu=await _carregar_user(db, fin)
    )
    assert rel["resumo"]["reembolsos"] == 250.0
    assert rel["resumo"]["resultado_liquido"] == 0.0
