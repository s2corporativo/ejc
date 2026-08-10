"""DataJud: invariantes de sincronização e contenção P0 de prazos.

O DataJud é fonte de movimentações. Até o motor auditável da Issue #968 existir,
o serviço-base não pode derivar vencimento nem persistir ``Deadline`` a partir
da data/nome de um movimento — independentemente de startup web ou monkeypatch.

Os testes DB-level exigem PostgreSQL (RUN_DB_TESTS=1); os demais são puros.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.services import datajud_service
from app.services.datajud_service import _ref_datajud


# ── Compatibilidade da referência legada ──────────────────────────────────────

def test_ref_datajud_estavel_e_ignora_mascara_do_cnj():
    a = _ref_datajud("0000001-02.2020.8.13.0000", "2026-07-05", "Contestacao")
    b = _ref_datajud("0000001022020813000-0", "2026-07-05", "Contestacao")
    assert a == b


def test_ref_datajud_muda_com_titulo_ou_data():
    base = _ref_datajud("0000001-02.2020.8.13.0000", "2026-07-05", "Contestacao")
    assert base != _ref_datajud(
        "0000001-02.2020.8.13.0000", "2026-07-06", "Contestacao"
    )
    assert base != _ref_datajud(
        "0000001-02.2020.8.13.0000", "2026-07-05", "Replica"
    )


# ── P0 #968: o serviço-base não é produtor de prazo ──────────────────────────

def test_servico_base_nao_contem_motor_legado_de_vencimento():
    origem = Path(datajud_service.__file__).read_text(encoding="utf-8")

    assert "_MOVIMENTOS_CRITICOS" not in origem
    assert "prazo_dias_uteis" not in origem
    assert "db.add(Deadline" not in origem


def test_detector_compativel_e_fail_safe_nao_sugere_vencimento():
    assert datajud_service._detectar_prazos_criticos(
        "Sentença proferida — intimação para manifestação",
        None,
    ) == []


@pytest.mark.asyncio
async def test_sync_prazos_requer_revisao_e_nao_toca_banco():
    class _DBProibido:
        def __getattr__(self, nome):
            raise AssertionError(f"sincronização de prazo tentou acessar DB: {nome}")

    resultado = await datajud_service.sincronizar_prazos_datajud(
        "caso-1",
        "0000001-02.2020.8.13.0000",
        _DBProibido(),
    )

    assert resultado["criados"] == 0
    assert resultado["encontrados"] == 0
    assert resultado["erro"] is None
    assert resultado["revisao_necessaria"] is True
    assert resultado["motivo"] == datajud_service.PRAZO_DATAJUD_MOTIVO_BLOQUEIO


# ── Regressões DB-level ───────────────────────────────────────────────────────

dblevel = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def _criar_caso_teste(db, *, numero_processo: str) -> tuple[str, str]:
    tok = uuid4().hex[:8]
    cli = str(uuid4())
    caso = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO clients (id, tipo, nome, email, status) "
            "VALUES (:id, 'PF', :nome, :email, 'ativo')"
        ),
        {
            "id": cli,
            "nome": f"Cliente DJ {tok}",
            "email": f"{tok}@teste.local",
        },
    )
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id, "
            "numero_processo, sync_pending) VALUES "
            "(:id, :tit, 'civil', 'em_instrucao', :cli, :numero, TRUE)"
        ),
        {
            "id": caso,
            "tit": f"Caso DJ {tok}",
            "cli": cli,
            "numero": numero_processo,
        },
    )
    await db.commit()
    return cli, caso


async def _limpar_caso_teste(db, *, cli: str, caso: str) -> None:
    await db.rollback()
    await db.execute(text("DELETE FROM deadlines WHERE case_id = :c"), {"c": caso})
    await db.execute(text("DELETE FROM case_movimentos WHERE case_id = :c"), {"c": caso})
    await db.execute(text("DELETE FROM cases WHERE id = :c"), {"c": caso})
    await db.execute(text("DELETE FROM clients WHERE id = :c"), {"c": cli})
    await db.commit()


@dblevel
async def test_sincronizar_caso_zera_sync_pending_sem_prazo(monkeypatch):
    from app.core.database import AsyncSessionLocal
    from app.models.case import Case

    async def _fake_consulta(_numero):
        return {"movimentos": []}

    monkeypatch.setattr(datajud_service, "consultar_processo", _fake_consulta)

    async with AsyncSessionLocal() as db:
        cli, caso = await _criar_caso_teste(
            db,
            numero_processo="0000001-02.2020.8.13.0000",
        )
        try:
            case = (
                await db.execute(select(Case).where(Case.id == caso))
            ).scalar_one()
            assert case.sync_pending is True

            await datajud_service.sincronizar_caso(db, case)

            assert case.sync_pending is False
            assert case.last_synced_at is not None
        finally:
            await _limpar_caso_teste(db, cli=cli, caso=caso)


@dblevel
async def test_movimento_com_texto_critico_nao_cria_deadline(monkeypatch):
    from app.core.database import AsyncSessionLocal
    from app.models.case import Case

    async def _fake_consulta(_numero):
        return {
            "movimentos": [
                {
                    "data": "2026-07-05",
                    "descricao": "Sentença proferida — intimação para manifestação",
                }
            ]
        }

    monkeypatch.setattr(datajud_service, "consultar_processo", _fake_consulta)

    async with AsyncSessionLocal() as db:
        cli, caso = await _criar_caso_teste(
            db,
            numero_processo="0000001-02.2020.8.13.0000",
        )
        try:
            case = (
                await db.execute(select(Case).where(Case.id == caso))
            ).scalar_one()

            inseridos = await datajud_service.sincronizar_caso(db, case)
            await db.flush()

            qtd_movimentos = (
                await db.execute(
                    text("SELECT COUNT(*) FROM case_movimentos WHERE case_id = :c"),
                    {"c": caso},
                )
            ).scalar_one()
            qtd_prazos = (
                await db.execute(
                    text("SELECT COUNT(*) FROM deadlines WHERE case_id = :c"),
                    {"c": caso},
                )
            ).scalar_one()

            assert inseridos == 1
            assert qtd_movimentos == 1
            assert qtd_prazos == 0
        finally:
            await _limpar_caso_teste(db, cli=cli, caso=caso)
