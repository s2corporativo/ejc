"""RBAC da responsabilidade de prazo criada pela Entrada Única.

O teste existe porque ROLE_LEVEL não representa pertencimento funcional:
``financeiro`` tem nível numérico maior que ``estagiario``, mas não integra a
equipe jurídica e não pode receber prazo jurídico.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.case import Case, CaseMovimento, CaseParte
from app.models.client import Client
from app.models.deadline import Deadline
from app.models.document import Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem
from app.models.user import User, UserRole
from app.schemas.entrada import CriarCasoEntradaRequest
from app.services import entrada_service

_TABELAS = [
    User.__table__,
    Client.__table__,
    Case.__table__,
    CaseMovimento.__table__,
    Document.__table__,
    DocumentIntakeBatch.__table__,
    DocumentIntakeItem.__table__, Deadline.__table__,
    CaseParte.__table__,
]


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _numero(_db):
        return f"DPT-TEST-{uuid4().hex[:8]}"

    async def _audit(*args, **kwargs):
        return None

    monkeypatch.setattr(entrada_service, "proximo_numero_interno", _numero)
    monkeypatch.setattr(entrada_service, "criar_audit_log", _audit)

    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(db, role: UserRole) -> tuple[User, str, str]:
    advogado = User(
        id=str(uuid4()),
        email=f"adv-{uuid4().hex[:8]}@teste.local",
        hashed_password="x",
        full_name="Advogado Responsável",
        role=UserRole.advogado,
        is_active=True,
    )
    alvo = User(
        id=str(uuid4()),
        email=f"alvo-{uuid4().hex[:8]}@teste.local",
        hashed_password="x",
        full_name=f"Responsável {role.value}",
        role=role,
        is_active=True,
    )
    batch_id = str(uuid4())
    batch = DocumentIntakeBatch(
        id=batch_id,
        status="concluido",
        created_by=advogado.id,
        document_count=0,
        resultado={"entrada_unica": {"rascunho_id": batch_id}},
    )
    db.add_all([advogado, alvo, batch])
    await db.commit()
    return advogado, alvo.id, batch_id


def _payload(advogado_id: str, responsavel_prazo_id: str) -> CriarCasoEntradaRequest:
    return CriarCasoEntradaRequest(
        cliente={"novo_nome": f"Cliente {uuid4().hex[:8]}"},
        area="civil",
        titulo="Caso de RBAC de prazo",
        fatos="Fatos revisados.",
        documentos_ids=[],
        advogado_responsavel_id=advogado_id,
        confirmo_dados_revisados=True,
        duplicate_confirmed=True,
        conflict_confirmed=True,
        prazo={
            "titulo": "Prazo processual",
            "data": date(2026, 9, 1),
            "responsavel_id": responsavel_prazo_id,
        },
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "role",
    [UserRole.financeiro, UserRole.secretaria, UserRole.cliente_externo],
)
async def test_perfis_fora_da_equipe_juridica_nao_recebem_prazo(db, role):
    advogado, alvo_id, batch_id = await _seed(db, role)

    with pytest.raises(HTTPException) as exc:
        await entrada_service.criar_caso_do_rascunho(
            db,
            advogado,
            batch_id,
            _payload(advogado.id, alvo_id),
        )
    assert exc.value.status_code == 422
    assert "equipe jurídica" in str(exc.value.detail)
    await db.rollback()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "role",
    [UserRole.estagiario, UserRole.advogado_auxiliar, UserRole.advogado],
)
async def test_equipe_juridica_ativa_pode_receber_prazo(db, role):
    advogado, alvo_id, batch_id = await _seed(db, role)

    result = await entrada_service.criar_caso_do_rascunho(
        db,
        advogado,
        batch_id,
        _payload(advogado.id, alvo_id),
    )
    await db.commit()

    prazo = await db.get(Deadline, result["deadline_id"])
    assert prazo is not None
    assert prazo.responsavel_id == alvo_id
