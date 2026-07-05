"""Inadimplência: faixas de nível (puro) + regressão do refresh de days_overdue.

O bug corrigido: o alerta só atualizava days_overdue/amount_due quando o NÍVEL
mudava; um alerta parado na mesma faixa (ex.: 'medio', 30-59d) congelava o
days_overdue no valor de entrada na faixa, e o painel de cobrança (ordenado por
days_overdue) exibia dias em atraso desatualizados.

O teste de regressão exige Postgres (RUN_DB_TESTS=1) — os demais são puros.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.services.inadimplencia_service import _nivel


# ── Faixas de nível (função pura) ───────────────────────────────────────────────

def test_nivel_faixas():
    assert _nivel(0) == "leve"
    assert _nivel(14) == "leve"
    assert _nivel(29) == "leve"
    assert _nivel(30) == "medio"
    assert _nivel(59) == "medio"
    assert _nivel(60) == "critico"
    assert _nivel(89) == "critico"
    assert _nivel(90) == "cobranca_formal"
    assert _nivel(365) == "cobranca_formal"


# ── Regressão: refresh de days_overdue mesmo sem troca de nível (dblevel) ────────

dblevel = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


@dblevel
async def test_varrer_refresca_days_overdue_sem_trocar_nivel():
    from app.core.database import AsyncSessionLocal
    from app.services.inadimplencia_service import varrer_inadimplencia

    tok = uuid4().hex[:8]
    cli = str(uuid4())
    fee = str(uuid4())
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("INSERT INTO clients (id, tipo, nome, email, status) "
                 "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
            {"id": cli, "nome": f"Cliente Inad {tok}", "email": f"{tok}@teste.local"},
        )
        # Fee vencida há ~45 dias → faixa 'medio' (30-59).
        await db.execute(
            text("INSERT INTO fees (id, tipo, status, descricao, valor, "
                 "data_vencimento, client_id) VALUES "
                 "(:id, 'fixo', 'pendente', :desc, 1000, CURRENT_DATE - 45, :cli)"),
            {"id": fee, "desc": f"Honorario {tok}", "cli": cli},
        )
        await db.commit()
        try:
            # 1ª varredura: cria o alerta com days_overdue ~45.
            await varrer_inadimplencia(db)
            r = await db.execute(text(
                "SELECT alert_level, days_overdue FROM inadimplencia_alerts "
                "WHERE fee_id = :f AND resolved = FALSE"), {"f": fee})
            alerta = r.fetchone()
            assert alerta is not None
            assert alerta.alert_level == "medio"
            assert alerta.days_overdue >= 40

            # Simula um alerta com days_overdue congelado (como no bug).
            await db.execute(text(
                "UPDATE inadimplencia_alerts SET days_overdue = 30 "
                "WHERE fee_id = :f AND resolved = FALSE"), {"f": fee})
            await db.commit()

            # 2ª varredura: mesmo nível ('medio'), mas days_overdue deve refrescar.
            await varrer_inadimplencia(db)
            r2 = await db.execute(text(
                "SELECT alert_level, days_overdue FROM inadimplencia_alerts "
                "WHERE fee_id = :f AND resolved = FALSE"), {"f": fee})
            alerta2 = r2.fetchone()
            assert alerta2.alert_level == "medio"       # nível não mudou
            assert alerta2.days_overdue >= 40           # ...mas foi atualizado
        finally:
            await db.execute(text("DELETE FROM inadimplencia_alerts WHERE fee_id = :f"), {"f": fee})
            await db.execute(text("DELETE FROM fees WHERE id = :f"), {"f": fee})
            await db.execute(text("DELETE FROM clients WHERE id = :c"), {"c": cli})
            await db.commit()
