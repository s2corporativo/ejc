# -*- coding: utf-8 -*-
"""Exclusões RECUSADAS (422) devem gerar evento DELETE_RECUSADO em audit_logs.

Mesmo padrão dos demais *_dblevel.py da suíte: chama o handler do router
diretamente com AsyncSessionLocal; sem RUN_DB_TESTS=1, pula.

Cobertura:
- recusa por motivo ausente/curto → DELETE_RECUSADO com detalhes do motivo
- recusa por pendências → DELETE_RECUSADO com contagem e tipos de pendência
- exclusão bem-sucedida → DELETE (comportamento preservado, regressão)
- evento RECUSADO nunca cria soft delete (deleted_at permanece nulo)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "admin") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Recusado Teste', :role, true)"),
        {"id": uid, "email": f"recusado-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db, nome: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(db, client_id: str, titulo: str, resp_id: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "advogado_responsavel_id, created_at) "
             "VALUES (:id, :titulo, 'trabalhista', 'em_instrucao', :client_id, "
             ":resp_id, :now)"),
        {"id": cid, "titulo": titulo, "client_id": client_id,
         "resp_id": resp_id, "now": datetime.now(timezone.utc)},
    )
    return cid


def _user_mock(user_id: str, role: str = "admin"):
    """Usuário mínimo suficiente para os Depends(require_roles) do router."""
    from types import SimpleNamespace
    return SimpleNamespace(id=user_id, role=SimpleNamespace(value=role))


@pytest.mark.anyio
async def test_recusa_motivo_ausente_gera_delete_recusado():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        cid_cli = await _criar_cliente(db, "Cliente Recusado Motivo")
        cid_caso = await _criar_caso(db, cid_cli, "Recusado Motivo", uid)
        await db.commit()

        from app.models.case import Case
        from app.routers.cases import excluir

        # db2 simula a transação da requisição (com rollback ao sair com
        # exceção, como get_db). A trilha da recusa é commitada em transação
        # própria, portanto persiste mesmo após o rollback de db2.
        from app.core.database import AsyncSessionLocal as ASL
        async with ASL() as db2:
            cu = _user_mock(uid)
            with pytest.raises(Exception) as exc_info:
                await excluir(case_id=cid_caso, motivo=None,
                              payload=None, db=db2, cu=cu)
            assert getattr(exc_info.value, "status_code", None) == 422

        # db3: leitura isolada, imune ao rollback de db2 e de db.
        async with ASL() as db3:
            from app.models.audit_log import AuditLog
            log = (await db3.execute(select(AuditLog).where(
                AuditLog.acao == "DELETE_RECUSADO",
                AuditLog.entidade == "cases",
                AuditLog.registro_id == cid_caso,
            ))).scalar_one_or_none()
            assert log is not None, "DELETE_RECUSADO não foi registrado"
            assert "motivo" in (log.detalhes or "").lower()

        caso = (await db.execute(select(Case).where(Case.id == cid_caso))).scalar_one()
        assert caso.deleted_at is None, "caso não pode sofrer soft delete em recusa"


@pytest.mark.anyio
async def test_recusa_pendencias_gera_delete_recusado():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        cid_cli = await _criar_cliente(db, "Cliente Recusado Prazo")
        cid_caso = await _criar_caso(db, cid_cli, "Recusado Prazo", uid)
        did = str(uuid4())
        await db.execute(
            text("INSERT INTO deadlines (id, case_id, titulo, tipo, prioridade, "
                 "status, data_prazo, created_at) "
                 "VALUES (:id, :case_id, :titulo, 'processual', 'media', "
                 "'pendente', '2026-12-01', :now)"),
            {"id": did, "case_id": cid_caso, "titulo": "Prazo pendente teste",
             "now": datetime.now(timezone.utc)},
        )
        await db.commit()

        from app.models.case import Case
        from app.routers.cases import excluir

        # Nova sessão para simular chamada HTTP real (mesmo comportamento da
        # aplicação: o endpoint abre transação própria, cria o log e faz
        # rollback/commit pela camada superior).
        from app.core.database import AsyncSessionLocal as ASL
        async with ASL() as db2:
            cu = _user_mock(uid)
            with pytest.raises(Exception) as exc_info:
                await excluir(case_id=cid_caso,
                              motivo="motivo valido de teste",
                              payload=None, db=db2, cu=cu)
            assert getattr(exc_info.value, "status_code", None) == 422
        db.rollback()

        # db3: leitura isolada, imune ao rollback de db2 e de db.
        async with ASL() as db3:
            from app.models.audit_log import AuditLog
            log = (await db3.execute(select(AuditLog).where(
                AuditLog.acao == "DELETE_RECUSADO",
                AuditLog.entidade == "cases",
                AuditLog.registro_id == cid_caso,
            ))).scalar_one_or_none()
            assert log is not None, "DELETE_RECUSADO não foi persistido (commit ausente)"
            det = (log.detalhes or "").lower()
            assert "pendência" in det
            assert "prazo" in det

        caso = (await db.execute(select(Case).where(Case.id == cid_caso))).scalar_one()
        assert caso.deleted_at is None
        await db.rollback()
        return


@pytest.mark.anyio
async def test_exclusao_sucesso_gera_delete_ordinario():
    """Regressão: exclusão aprovada continua gerando DELETE, não RECUSADO."""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        cid_cli = await _criar_cliente(db, "Cliente Exclusao Sucesso")
        cid_caso = await _criar_caso(db, cid_cli, "Sucesso", uid)
        await db.commit()

        from app.models.case import Case
        from app.routers.cases import excluir

        # Nova sessão (comportamento real do endpoint: transação própria).
        from app.core.database import AsyncSessionLocal as ASL
        async with ASL() as db2:
            cu = _user_mock(uid)
            await excluir(case_id=cid_caso,
                                 motivo="motivo valido de teste",
                                 payload=None, db=db2, cu=cu)
            db2.commit()

        from app.models.audit_log import AuditLog
        acoes = {
            log.acao for log in
            (await db.execute(select(AuditLog).where(
                AuditLog.registro_id == cid_caso))).scalars().all()
        }
        assert "DELETE" in acoes
        assert "DELETE_RECUSADO" not in acoes

        caso = (await db.execute(select(Case).where(Case.id == cid_caso))).scalar_one()
        assert caso.deleted_at is not None, "soft delete deve ocorrer no sucesso"
