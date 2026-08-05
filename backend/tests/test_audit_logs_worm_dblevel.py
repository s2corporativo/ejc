"""Nível de banco (Postgres real) — trigger WORM de `audit_logs` (Issue #699).

Prova COMPORTAMENTAL (não `inspect.getsource`) de que `UPDATE`/`DELETE`
diretos em `audit_logs` falham contra PostgreSQL de verdade, imposta pela
migration `131_audit_logs_worm` (trigger `trg_audit_logs_bloqueia_mutacao`).

Cobre também:
- `INSERT` via `criar_audit_log` (o único caminho de escrita usado pela
  aplicação) continua funcionando sem regressão.
- a via privilegiada de expurgo (`SET LOCAL ejc.audit_logs_permitir_expurgo
  = 'on'`) existe e funciona DENTRO da transação que a declara, mas não
  vaza para a transação seguinte — ela fica pronta para a futura Issue #582
  (purga LGPD com preservação legal), sem que este PR implemente expurgo.

Requer RUN_DB_TESTS=1 com Postgres real e migrations aplicadas (mesmo padrão
dos demais `*_dblevel.py` da suíte); pula silenciosamente sem isso — nunca
toca banco de produção.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from ._audit_utils import expurgar_audit_por_registro

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL com migrations (RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _isolar_pool_por_event_loop():
    from app.core.database import engine

    await engine.dispose(close=False)
    yield
    await engine.dispose(close=False)


async def _inserir_log_cru(db, log_id: str) -> None:
    await db.execute(
        text(
            "INSERT INTO audit_logs (id, acao, entidade) "
            "VALUES (:id, 'CREATE', 'clients')"
        ),
        {"id": log_id},
    )
    await db.commit()


async def _apagar_via_bypass(db, log_id: str) -> None:
    """Limpeza de teste pela via privilegiada. NÃO é a implementação de
    expurgo da #582 — só evita deixar lixo na base usada pelos testes."""
    await expurgar_audit_por_registro(db, "id = :id", {"id": log_id})
    await db.commit()


@pytest.mark.asyncio
async def test_update_direto_falha_contra_postgres_real():
    from app.core.database import AsyncSessionLocal

    log_id = str(uuid4())
    async with AsyncSessionLocal() as db:
        await _inserir_log_cru(db, log_id)
        try:
            with pytest.raises(DBAPIError, match="imutavel"):
                await db.execute(
                    text("UPDATE audit_logs SET detalhes = 'hack' WHERE id = :id"),
                    {"id": log_id},
                )
        finally:
            await db.rollback()

    async with AsyncSessionLocal() as db:
        # a linha sobreviveu ao UPDATE rejeitado — confirma antes de limpar.
        r = await db.execute(
            text("SELECT detalhes FROM audit_logs WHERE id = :id"), {"id": log_id}
        )
        assert r.scalar_one() is None
        await _apagar_via_bypass(db, log_id)


@pytest.mark.asyncio
async def test_delete_direto_falha_contra_postgres_real():
    from app.core.database import AsyncSessionLocal

    log_id = str(uuid4())
    async with AsyncSessionLocal() as db:
        await _inserir_log_cru(db, log_id)
        try:
            with pytest.raises(DBAPIError, match="imutavel"):
                await db.execute(
                    text("DELETE FROM audit_logs WHERE id = :id"), {"id": log_id}
                )
        finally:
            await db.rollback()

    async with AsyncSessionLocal() as db:
        r = await db.execute(
            text("SELECT count(*) FROM audit_logs WHERE id = :id"), {"id": log_id}
        )
        assert r.scalar_one() == 1, "linha deveria ter sobrevivido ao DELETE rejeitado"
        await _apagar_via_bypass(db, log_id)


@pytest.mark.asyncio
async def test_truncate_direto_falha_contra_postgres_real():
    """TRUNCATE não dispara o trigger de linha (BEFORE UPDATE OR DELETE) —
    precisa do trigger dedicado de STATEMENT (`trg_audit_logs_bloqueia_truncate`,
    migration `131_audit_logs_worm`). Sem ele, `TRUNCATE audit_logs` apaga a
    trilha inteira contornando por completo o bloqueio de UPDATE/DELETE."""
    from app.core.database import AsyncSessionLocal

    log_id = str(uuid4())
    async with AsyncSessionLocal() as db:
        await _inserir_log_cru(db, log_id)
        try:
            with pytest.raises(DBAPIError, match="imutavel"):
                await db.execute(text("TRUNCATE audit_logs"))
        finally:
            await db.rollback()

    async with AsyncSessionLocal() as db:
        r = await db.execute(
            text("SELECT count(*) FROM audit_logs WHERE id = :id"), {"id": log_id}
        )
        assert r.scalar_one() == 1, "linha deveria ter sobrevivido ao TRUNCATE rejeitado"
        await _apagar_via_bypass(db, log_id)


@pytest.mark.asyncio
async def test_truncate_com_bypass_de_expurgo_funciona():
    """A via privilegiada de expurgo (Issue #582, reservada e INATIVA neste
    PR) também precisa cobrir TRUNCATE, não só UPDATE/DELETE.

    TRUNCATE é transacional no Postgres — usa ROLLBACK ao final, em vez de
    COMMIT, para provar que o bypass permite a operação sem de fato apagar a
    tabela inteira compartilhada com o resto da suíte de testes."""
    from app.core.database import AsyncSessionLocal

    log_id = str(uuid4())
    async with AsyncSessionLocal() as db:
        await _inserir_log_cru(db, log_id)

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
            # Não levanta exceção com o bypass ligado — é a asserção do teste.
            await db.execute(text("TRUNCATE audit_logs"))
            r = await db.execute(
                text("SELECT count(*) FROM audit_logs WHERE id = :id"), {"id": log_id}
            )
            assert r.scalar_one() == 0, "TRUNCATE com bypass deveria ter apagado a linha"
            await db.rollback()
    finally:
        async with AsyncSessionLocal() as db:
            await _apagar_via_bypass(db, log_id)


@pytest.mark.asyncio
async def test_criar_audit_log_continua_funcionando_sem_regressao():
    """`criar_audit_log` (backend/app/models/audit_log.py:31-56) é o único
    caminho de escrita usado pelos ~77 chamadores do app — precisa continuar
    fazendo INSERT normalmente com o trigger instalado."""
    from app.core.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog, criar_audit_log

    marcador = f"worm-dblevel-{uuid4()}"
    async with AsyncSessionLocal() as db:
        await criar_audit_log(
            db,
            user_id=None,
            user_role=None,
            acao="LOGIN",
            entidade="auth",
            detalhes=marcador,
            ip="127.0.0.1",
        )
        await db.commit()

        row = (
            await db.execute(
                select(AuditLog).where(AuditLog.detalhes == marcador)
            )
        ).scalar_one()
        assert row.acao == "LOGIN"
        assert row.entidade == "auth"

        await _apagar_via_bypass(db, row.id)


@pytest.mark.asyncio
async def test_bypass_de_expurgo_nao_vaza_para_a_proxima_transacao():
    """A GUC de sessão só abre a exceção DENTRO da transação que a declara
    (`SET LOCAL`) — prova que a via reservada para a #582 não vira um
    interruptor permanente por engano."""
    from app.core.database import AsyncSessionLocal

    log_id = str(uuid4())
    async with AsyncSessionLocal() as db:
        await _inserir_log_cru(db, log_id)
        # remove pela via privilegiada — commita a transação com o bypass.
        await _apagar_via_bypass(db, log_id)

        # nova transação NA MESMA sessão, sem SET LOCAL: o bypass anterior
        # não deve valer mais.
        outro_id = str(uuid4())
        await _inserir_log_cru(db, outro_id)
        try:
            with pytest.raises(DBAPIError, match="imutavel"):
                await db.execute(
                    text("DELETE FROM audit_logs WHERE id = :id"), {"id": outro_id}
                )
        finally:
            await db.rollback()

    async with AsyncSessionLocal() as db:
        await _apagar_via_bypass(db, outro_id)
