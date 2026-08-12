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

_TABELAS = [
    Document.__table__,
    DocumentIntakeBatch.__table__,
    DocumentIntakeItem.__table__,
]


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






