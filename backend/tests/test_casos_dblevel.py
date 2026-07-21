"""R2 — Arquivamento (reversível) e exclusão segura de caso — validação ROW-LEVEL.

Porta a cobertura do antigo `test_casos.py` (removido na integração do redesign,
que usava fixtures API-level de um `tests/conftest.py` hoje inexistente) para o
padrão DB-level da suíte atual: Postgres real, `AsyncSessionLocal`, chamando os
handlers do router diretamente. Mesmo gate de CI dos demais *_dblevel.py.

Requer Postgres com migrations aplicadas (RUN_DB_TESTS=1). Sem isso, pula —
nunca conecta em produção.
"""
from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_cliente(db, client_id):
    # Cutover C6/LGPD: sem coluna cpf em texto puro. Este teste não usa o
    # documento — insere só o cadastro mínimo.
    await db.execute(
        text(
            "INSERT INTO clients (id, tipo, nome, email, status) "
            "VALUES (:id, 'PF', 'Cliente Caso R2', :email, 'ativo')"
        ),
        {"id": client_id, "email": f"{client_id[:8]}@teste.local"},
    )


async def _criar_socio(db) -> str:
    """Executor com role 'socio' (dentro de _ARQUIVAMENTO_ROLES e admin/socio do
    delete). Precisa existir de verdade: audit_logs.user_id e
    case_movimentos.created_by têm FK real para users.id."""
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Sócio Teste R2', 'socio', true)"
        ),
        {"id": uid, "email": f"socio-{uid[:8]}@teste.local"},
    )
    return uid


async def _criar_caso(db, case_id, client_id, status="ativo"):
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id) "
            "VALUES (:id, 'Caso Teste R2', 'civil', :status, :cid)"
        ),
        {"id": case_id, "status": status, "cid": client_id},
    )


async def _criar_prazo_pendente(db, case_id):
    """Prazo pendente → deve bloquear a exclusão (422)."""
    await db.execute(
        text(
            "INSERT INTO deadlines (id, titulo, tipo, prioridade, status, data_prazo, "
            "case_id, origem) VALUES (:id, 'Contestação', 'processual', 'media', "
            "'pendente', :dp, :cid, 'manual')"
        ),
        {"id": str(uuid4()), "dp": date(2030, 1, 1), "cid": case_id},
    )


async def _carregar_user(db, uid):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, client_id, case_id, user_id):
    # Ordem por FK: filhos → caso → usuário → cliente.
    await db.execute(text("DELETE FROM case_movimentos WHERE case_id = :id"), {"id": case_id})
    await db.execute(text("DELETE FROM deadlines WHERE case_id = :id"), {"id": case_id})
    await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": user_id})
    await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": case_id})
    await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    """Evita 'Event loop is closed' entre testes async (loop por função)."""
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_arquivar_e_desarquivar_caso():
    from app.core.database import AsyncSessionLocal
    from app.models.case import CaseStatus
    from app.routers.cases import arquivar_caso, desarquivar_caso

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id)
        uid = await _criar_socio(db)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            # Arquiva com motivo → status arquivado + archived_at + archive_reason.
            from app.routers.cases import ArchiveCaseRequest
            c = await arquivar_caso(
                case_id=case_id, background=BackgroundTasks(),
                payload=ArchiveCaseRequest(motivo="cliente encerrou o contrato"),
                db=db, cu=cu,
            )
            assert c.status == CaseStatus.arquivado
            assert c.archived_at is not None
            assert c.archive_reason == "cliente encerrou o contrato"

            # Desarquiva → volta a ativo, limpa archived_at/archive_reason.
            c2 = await desarquivar_caso(
                case_id=case_id, background=BackgroundTasks(), db=db, cu=cu
            )
            assert c2.status == CaseStatus.ativo
            assert c2.archived_at is None
            assert c2.archive_reason is None
        finally:
            await _limpar(db, client_id, case_id, uid)


async def test_arquivar_ja_arquivado_da_409():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import arquivar_caso

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="arquivado")
        uid = await _criar_socio(db)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            with pytest.raises(HTTPException) as exc:
                await arquivar_caso(
                    case_id=case_id, background=BackgroundTasks(),
                    payload=None, db=db, cu=cu,
                )
            assert exc.value.status_code == 409
        finally:
            await _limpar(db, client_id, case_id, uid)


async def test_excluir_sem_motivo_da_422():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import excluir

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id)
        uid = await _criar_socio(db)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            with pytest.raises(HTTPException) as exc:
                await excluir(case_id=case_id, motivo=None, payload=None, db=db, cu=cu)
            assert exc.value.status_code == 422

            # Caso NÃO foi excluído — dado preservado.
            row = (await db.execute(
                text("SELECT deleted_at FROM cases WHERE id = :id"), {"id": case_id}
            )).mappings().first()
            assert row["deleted_at"] is None
        finally:
            await _limpar(db, client_id, case_id, uid)


async def test_excluir_com_prazo_pendente_bloqueia():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import excluir

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id)
        await _criar_prazo_pendente(db, case_id)
        uid = await _criar_socio(db)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            with pytest.raises(HTTPException) as exc:
                await excluir(
                    case_id=case_id, motivo="motivo suficiente aqui",
                    payload=None, db=db, cu=cu,
                )
            assert exc.value.status_code == 422
            # O detalhe lista as pendências (prazo).
            detail = exc.value.detail
            assert isinstance(detail, dict) and detail.get("pendencias")
            assert any(p["tipo"] == "prazo" for p in detail["pendencias"])

            # Bloqueado → caso preservado.
            row = (await db.execute(
                text("SELECT deleted_at FROM cases WHERE id = :id"), {"id": case_id}
            )).mappings().first()
            assert row["deleted_at"] is None
        finally:
            await _limpar(db, client_id, case_id, uid)


async def test_excluir_sem_pendencias_soft_delete():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import excluir

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id)
        uid = await _criar_socio(db)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            resp = await excluir(
                case_id=case_id, motivo="encerramento sem pendências",
                payload=None, db=db, cu=cu,
            )
            assert "excluído" in resp.detail.lower()

            # Soft delete: deleted_at preenchido (restaurável pela lixeira).
            row = (await db.execute(
                text("SELECT deleted_at FROM cases WHERE id = :id"), {"id": case_id}
            )).mappings().first()
            assert row["deleted_at"] is not None
        finally:
            await _limpar(db, client_id, case_id, uid)
