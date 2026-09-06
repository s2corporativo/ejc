"""DB-14 — relatório de retenção LGPD: identifica e reporta, nunca apaga.

Parte pura (sem banco): o resumo do heartbeat carrega só contagens.
Parte ROW-LEVEL (RUN_DB_TESTS=1): casos encerrados antigos, clientes
inativos sem caso aberto e leads sem conversão entram no relatório; caso
aberto protege o cliente; nada é alterado no banco.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.services import retencao_lgpd_service as svc


def test_resumo_heartbeat_so_contagens_sem_ids():
    rel = {
        "acao": svc.ACAO,
        "casos_encerrados_alem_prazo": {"total": 3, "amostra_ids": ["a", "b", "c"]},
        "clientes_inativos_alem_prazo": {"total": 1, "amostra_ids": ["x"]},
        "leads_sem_conversao_alem_prazo": {"total": 0, "amostra_ids": []},
        "dpt360_a_anonimizar": {"total": 2, "amostra_ids": ["k"]},
        "dpt360_a_expurgar": {"total": 0, "amostra_ids": []},
        "total_alem_prazo": 6,
    }
    resumo = json.loads(svc.resumo_heartbeat(rel))
    assert resumo == {
        "casos_encerrados_alem_prazo": 3, "clientes_inativos_alem_prazo": 1,
        "leads_sem_conversao_alem_prazo": 0, "dpt360_a_anonimizar": 2,
        "dpt360_a_expurgar": 0, "total": 6, "acao": "somente_relatorio",
    }
    assert "amostra" not in svc.resumo_heartbeat(rel)
    assert len(svc.resumo_heartbeat(rel)) <= 500  # cabe no detail do heartbeat


def test_prazos_dpt360_vem_da_politica_em_codigo():
    from app.modules.dpt360 import lifecycle_service as lc
    assert svc._prazos_dpt360() == (lc.PRAZO_DESCARTADA, lc.PRAZO_ANONIMIZADA)


# ── ROW-LEVEL ────────────────────────────────────────────────────────────────

_dblevel = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _cliente(db, nome, status, dias_atras) -> str:
    cid = str(uuid4())
    quando = datetime.now(timezone.utc) - timedelta(days=dias_atras)
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, status, created_at, updated_at) "
             "VALUES (:id, 'PF', :nome, :status, :q, :q)"),
        {"id": cid, "nome": nome, "status": status, "q": quando},
    )
    return cid


async def _caso(db, client_id, status, dias_atras) -> str:
    case_id = str(uuid4())
    quando = datetime.now(timezone.utc) - timedelta(days=dias_atras)
    encerrado_em = quando if status in ("encerrado", "arquivado") else None
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, created_at, updated_at, "
             "data_encerramento) VALUES (:id, 'Caso retenção', 'civil', :status, :cid, :q, :q, :enc)"),
        {"id": case_id, "status": status, "cid": client_id, "q": quando, "enc": encerrado_em},
    )
    return case_id


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


@_dblevel
async def test_relatorio_identifica_sem_alterar_nada():
    from app.core.database import AsyncSessionLocal

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        # Além do prazo:
        c_inativo = await _cliente(db, f"Inativo {tok}", "inativo", 2000)
        caso_velho = await _caso(db, c_inativo, "encerrado", 2000)
        c_lead = await _cliente(db, f"Lead {tok}", "lead", 120)
        # Protegidos / dentro do prazo:
        c_protegido = await _cliente(db, f"Protegido {tok}", "inativo", 2000)
        caso_aberto = await _caso(db, c_protegido, "em_instrucao", 2000)
        c_recente = await _cliente(db, f"Recente {tok}", "inativo", 10)
        c_lead_novo = await _cliente(db, f"Lead novo {tok}", "lead", 5)
        c_ativo = await _cliente(db, f"Ativo {tok}", "ativo", 2000)
        await db.commit()
        try:
            antes = (await db.execute(
                text("SELECT count(*) FROM clients WHERE nome LIKE :p"), {"p": f"%{tok}"}
            )).scalar()

            rel = await svc.identificar_alem_do_prazo(db, amostra=1000)

            assert rel["acao"] == "somente_relatorio"
            assert caso_velho in rel["casos_encerrados_alem_prazo"]["amostra_ids"]
            assert caso_aberto not in rel["casos_encerrados_alem_prazo"]["amostra_ids"]
            inativos = rel["clientes_inativos_alem_prazo"]["amostra_ids"]
            assert c_inativo in inativos
            assert c_protegido not in inativos, "caso aberto protege o cliente"
            assert c_recente not in inativos and c_ativo not in inativos
            leads = rel["leads_sem_conversao_alem_prazo"]["amostra_ids"]
            assert c_lead in leads and c_lead_novo not in leads
            assert rel["total_alem_prazo"] >= 3
            for bloco in ("casos_encerrados_alem_prazo", "clientes_inativos_alem_prazo",
                          "leads_sem_conversao_alem_prazo"):
                assert rel[bloco]["total"] >= len(rel[bloco]["amostra_ids"]) >= 1
                assert set(rel[bloco]) == {"prazo_dias", "total", "amostra_ids"}

            # Nada apagado, nada anonimizado.
            depois = (await db.execute(
                text("SELECT count(*) FROM clients WHERE nome LIKE :p"), {"p": f"%{tok}"}
            )).scalar()
            assert depois == antes
            anon = (await db.execute(
                text("SELECT count(*) FROM clients WHERE nome LIKE :p AND anonimizado_em IS NOT NULL"),
                {"p": f"%{tok}"},
            )).scalar()
            assert anon == 0
        finally:
            await db.rollback()
            for case_id in (caso_velho, caso_aberto):
                await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": case_id})
            await db.execute(text("DELETE FROM clients WHERE nome LIKE :p"), {"p": f"%{tok}"})
            await db.commit()


@_dblevel
async def test_job_bate_ponto_com_resultado():
    from app.core.database import AsyncSessionLocal
    from app.services.heartbeat_service import JOB_RETENCAO_LGPD, JOBS_MONITORADOS

    assert JOB_RETENCAO_LGPD in JOBS_MONITORADOS
    rel = await svc.job_retencao_lgpd()
    assert rel["acao"] == "somente_relatorio"
    async with AsyncSessionLocal() as db:
        linha = (await db.execute(
            text("SELECT last_status, detail FROM scheduler_heartbeat WHERE job_name = :j"),
            {"j": JOB_RETENCAO_LGPD},
        )).one()
        assert linha.last_status == "ok"
        detalhe = json.loads(linha.detail)
        assert detalhe["acao"] == "somente_relatorio"
        assert detalhe["total"] == rel["total_alem_prazo"]
