"""Testes do ciclo de vida LGPD para oportunidades DPT360 (Issue #1086)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.document import Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem
from app.modules.dpt360.lifecycle_service import (
    ESTADO_TRIAGEM_PENDENTE,
    ESTADO_TRIAGEM_CONCLUIDA,
    ESTADO_DESCARTADA,
    ESTADO_EXPIRADA,
    ESTADO_ANONIMIZADA,
    ESTADO_CONVERTIDA,
    mudar_estado,
    anonimizar_oportunidade,
    expurgar_oportunidade,
    job_anonimizar_oportunidades,
    job_expurgar_oportunidades,
)

# AuditLog fica de fora: usa JSONB (Postgres-only) e não compila no SQLite —
# criar_audit_log é substituído por um coletor em memória (fixture _coletor_audit).
_TABELAS = [
    Document.__table__,
    DocumentIntakeBatch.__table__,
    DocumentIntakeItem.__table__,
]

_AUDITS: list = []


@pytest.fixture(autouse=True)
def _coletor_audit(monkeypatch):
    """AuditLog usa JSONB (Postgres-only): coletor em memória no lugar,
    seguindo a convenção de tests/test_entrada_unica.py do próprio repo."""

    async def _fake(*args, **kwargs):
        _AUDITS.append((args, kwargs))

    import app.modules.dpt360.lifecycle_service as _ls

    monkeypatch.setattr(_ls, "criar_audit_log", _fake)
    _AUDITS.clear()


@pytest.fixture
async def sessao_db():
    """Sessão de banco em memória para testes."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def user_id():
    return str(uuid4())


@pytest.fixture
async def oportunidade_nova(sessao_db, user_id):
    """Cria uma oportunidade em triagem_pendente."""
    batch = DocumentIntakeBatch(
        id=str(uuid4()),
        modalidade="dpt360_oportunidade",
        status="concluido",
        nivel_prontidao="triagem_pendente",
        document_count=0,
        total_bytes=0,
        created_by=user_id,
        ciclo_vida_estado=ESTADO_TRIAGEM_PENDENTE,
        resultado={
            "dpt360_opportunity": {
                "origem": "site_depaulateixeira",
                "email": "lead@example.com",
                "telefone": "+5511999999999",
                "mensagem": "Gostaria de orientação sobre contrato",
                "contato": "João Silva",
                "status": "triagem_pendente",
            }
        },
    )
    sessao_db.add(batch)
    await sessao_db.commit()
    await sessao_db.refresh(batch)
    return batch


@pytest.mark.asyncio
async def test_mudar_estado_invalido(sessao_db, oportunidade_nova, user_id):
    """Rejeita transição inválida (triagem_pendente → anonimizada)."""
    resultado = await mudar_estado(
        sessao_db,
        user_id=user_id,
        user_role="advogado",
        batch_id=oportunidade_nova.id,
        novo_estado=ESTADO_ANONIMIZADA,
    )

    assert resultado["erro"] == "transicao_invalida"
    assert resultado["estado_atual"] == ESTADO_TRIAGEM_PENDENTE
    assert ESTADO_ANONIMIZADA not in resultado["permitidas"]


@pytest.mark.asyncio
async def test_mudar_estado_oportunidade_convertida(
    sessao_db, oportunidade_nova, user_id
):
    """Protege oportunidade convertida (case_id preenchido) de mudança de estado."""
    oportunidade_nova.case_id = str(uuid4())
    await sessao_db.merge(oportunidade_nova)
    await sessao_db.commit()

    resultado = await mudar_estado(
        sessao_db,
        user_id=user_id,
        user_role="advogado",
        batch_id=oportunidade_nova.id,
        novo_estado=ESTADO_DESCARTADA,
    )

    assert resultado["erro"] == "oportunidade_ja_convertida"
    assert resultado["case_id"] == oportunidade_nova.case_id


@pytest.mark.asyncio
async def test_mudar_estado_triagem_pendente_para_concluida(
    sessao_db, oportunidade_nova, user_id
):
    """Transição válida: triagem_pendente → triagem_concluida com auditoria."""
    resultado = await mudar_estado(
        sessao_db,
        user_id=user_id,
        user_role="admin",
        batch_id=oportunidade_nova.id,
        novo_estado=ESTADO_TRIAGEM_CONCLUIDA,
        motivo="Análise completa",
    )

    assert resultado["sucesso"] is True
    assert resultado["estado_anterior"] == ESTADO_TRIAGEM_PENDENTE
    assert resultado["estado_novo"] == ESTADO_TRIAGEM_CONCLUIDA
    assert any("MUDAR_CICLO_VIDA" in (kw.get("acao") or "") for _, kw in _AUDITS)

    batch_atualizado = await sessao_db.get(DocumentIntakeBatch, oportunidade_nova.id)
    assert batch_atualizado.ciclo_vida_estado == ESTADO_TRIAGEM_CONCLUIDA
    assert batch_atualizado.triagem_concluida_por == user_id
    assert batch_atualizado.triagem_concluida_em is not None


@pytest.mark.asyncio
async def test_anonimizar_oportunidade_remove_pii(
    sessao_db, oportunidade_nova
):
    """Anonimização remove email/telefone/mensagem/contato, preserva origem/status."""
    batch_atualizado = await sessao_db.get(DocumentIntakeBatch, oportunidade_nova.id)
    batch_atualizado.ciclo_vida_estado = ESTADO_DESCARTADA
    batch_atualizado.ciclo_vida_updated_at = (
        datetime.now(timezone.utc) - timedelta(days=35)
    )
    await sessao_db.merge(batch_atualizado)
    await sessao_db.commit()

    resultado = await anonimizar_oportunidade(sessao_db, oportunidade_nova.id)

    assert resultado["sucesso"] is True
    assert "anonimizada_em" in resultado

    batch_anonimizado = await sessao_db.get(DocumentIntakeBatch, oportunidade_nova.id)
    assert batch_anonimizado.ciclo_vida_estado == ESTADO_ANONIMIZADA
    opp = batch_anonimizado.resultado.get("dpt360_opportunity", {})
    assert "email" not in opp
    assert "telefone" not in opp
    assert "mensagem" not in opp
    assert "contato" not in opp
    assert opp.get("origem") == "site_depaulateixeira"
    assert opp.get("status") == "triagem_pendente"


@pytest.mark.asyncio
async def test_job_anonimizar_dry_run(sessao_db, oportunidade_nova):
    """Job de anonimização com dry_run=True apenas conta."""
    batch_atualizado = await sessao_db.get(DocumentIntakeBatch, oportunidade_nova.id)
    batch_atualizado.ciclo_vida_estado = ESTADO_DESCARTADA
    batch_atualizado.ciclo_vida_updated_at = (
        datetime.now(timezone.utc) - timedelta(days=35)
    )
    await sessao_db.merge(batch_atualizado)
    await sessao_db.commit()

    resultado = await job_anonimizar_oportunidades(sessao_db, dry_run=True)

    assert resultado["dry_run"] is True
    assert resultado["anonimizadas"] == 1
    assert resultado["erros"] == 0

    batch_ainda_descartada = await sessao_db.get(DocumentIntakeBatch, oportunidade_nova.id)
    assert batch_ainda_descartada.ciclo_vida_estado == ESTADO_DESCARTADA
    assert batch_ainda_descartada.anonimizada_em is None


@pytest.mark.asyncio
async def test_job_anonimizar_executa(sessao_db, oportunidade_nova):
    """Job de anonimização com dry_run=False altera o estado."""
    batch_atualizado = await sessao_db.get(DocumentIntakeBatch, oportunidade_nova.id)
    batch_atualizado.ciclo_vida_estado = ESTADO_DESCARTADA
    batch_atualizado.ciclo_vida_updated_at = (
        datetime.now(timezone.utc) - timedelta(days=35)
    )
    await sessao_db.merge(batch_atualizado)
    await sessao_db.commit()

    resultado = await job_anonimizar_oportunidades(sessao_db, dry_run=False)

    assert resultado["dry_run"] is False
    assert resultado["anonimizadas"] == 1
    assert resultado["erros"] == 0

    batch_anonimizado = await sessao_db.get(DocumentIntakeBatch, oportunidade_nova.id)
    assert batch_anonimizado.ciclo_vida_estado == ESTADO_ANONIMIZADA
    assert batch_anonimizado.anonimizada_em is not None






