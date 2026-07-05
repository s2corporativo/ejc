"""DataJud: dedup de prazo (puro) + regressão do sync_pending.

Bug corrigido: em sincronizar_caso, os metadados de sync (sync_pending=False,
last_synced_at) só eram atualizados dentro de _criar_deadline_automatico, que
roda apenas quando há prazo crítico. Um caso sincronizado com sucesso e SEM
prazo (o caso comum) ficava com sync_pending=True para sempre.

O teste de regressão exige Postgres (RUN_DB_TESTS=1); os demais são puros.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.services.datajud_service import _ref_datajud


# ── Dedup de prazo (função pura) ────────────────────────────────────────────────

def test_ref_datajud_estavel_e_ignora_mascara_do_cnj():
    a = _ref_datajud("0000001-02.2020.8.13.0000", "2026-07-05", "Contestacao")
    b = _ref_datajud("0000001022020813000-0", "2026-07-05", "Contestacao")  # só dígitos
    # Mesmo CNJ (só muda a máscara) + mesma data + título → mesma chave.
    assert a == b


def test_ref_datajud_muda_com_titulo_ou_data():
    base = _ref_datajud("0000001-02.2020.8.13.0000", "2026-07-05", "Contestacao")
    assert base != _ref_datajud("0000001-02.2020.8.13.0000", "2026-07-06", "Contestacao")
    assert base != _ref_datajud("0000001-02.2020.8.13.0000", "2026-07-05", "Replica")


# ── Regressão dblevel: sync_pending zera em sync bem-sucedido sem prazo ──────────

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
async def test_sincronizar_caso_zera_sync_pending_sem_prazo(monkeypatch):
    from app.core.database import AsyncSessionLocal
    from app.models.case import Case
    from app.services import datajud_service

    # DataJud responde sucesso, porém SEM movimentos → nenhum prazo crítico.
    async def _fake_consulta(_numero):
        return {"movimentos": []}
    monkeypatch.setattr(datajud_service, "consultar_processo", _fake_consulta)

    tok = uuid4().hex[:8]
    cli = str(uuid4())
    caso = str(uuid4())
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("INSERT INTO clients (id, tipo, nome, email, status) "
                 "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
            {"id": cli, "nome": f"Cliente DJ {tok}", "email": f"{tok}@teste.local"},
        )
        await db.execute(
            text("INSERT INTO cases (id, titulo, area, status, client_id, "
                 "numero_processo, sync_pending) VALUES "
                 "(:id, :tit, 'civil', 'ativo', :cli, "
                 "'0000001-02.2020.8.13.0000', TRUE)"),
            {"id": caso, "tit": f"Caso DJ {tok}", "cli": cli},
        )
        await db.commit()
        try:
            case = (await db.execute(select(Case).where(Case.id == caso))).scalar_one()
            assert case.sync_pending is True  # começa "pendente"

            await datajud_service.sincronizar_caso(db, case)

            # Sucesso sem prazo: metadados DEVEM zerar (antes ficavam presos).
            assert case.sync_pending is False
            assert case.last_synced_at is not None
        finally:
            # sincronizar_caso alterou o ORM `case` SEM commitar; descarta esse
            # estado pendente antes de limpar por SQL cru, senão o commit final
            # tentaria flushar um UPDATE numa linha já apagada (StaleDataError).
            await db.rollback()
            await db.execute(text("DELETE FROM case_movimentos WHERE case_id = :c"), {"c": caso})
            await db.execute(text("DELETE FROM cases WHERE id = :c"), {"c": caso})
            await db.execute(text("DELETE FROM clients WHERE id = :c"), {"c": cli})
            await db.commit()
