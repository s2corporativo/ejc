"""#1398 — responsável de tarefa deve ser usuário interno, ativo e existente."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.task import Task
from app.models.user import User, UserRole
from app.routers import tasks as tasks_router


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(c, tables=[User.__table__, Task.__table__])
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _user(role: UserRole, *, active=True, deleted=False) -> User:
    uid = str(uuid4())
    return User(
        id=uid,
        email=f"{uid}@teste.local",
        hashed_password="h",
        full_name="Usuário Teste",
        role=role,
        is_active=active,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alvo",
    [
        lambda: _user(UserRole.cliente_externo),
        lambda: _user(UserRole.advogado, active=False),
        lambda: _user(UserRole.advogado, deleted=True),
    ],
)
async def test_post_rejeita_responsavel_externo_inativo_ou_excluido(db, alvo):
    criador = _user(UserRole.advogado)
    destino = alvo()
    db.add_all([criador, destino])
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await tasks_router.criar(
            tasks_router.TaskIn(titulo="Tarefa interna", responsavel_id=destino.id),
            db,
            criador,
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_patch_rejeita_responsavel_inexistente_sem_mutar_tarefa(db):
    criador = _user(UserRole.advogado)
    tarefa = Task(
        id=str(uuid4()),
        titulo="Original",
        responsavel_id=criador.id,
        criado_por=criador.id,
    )
    db.add_all([criador, tarefa])
    await db.commit()

    inexistente = str(uuid4())
    with pytest.raises(HTTPException) as exc:
        await tasks_router.atualizar(
            tarefa.id,
            tasks_router.TaskPatch(responsavel_id=inexistente),
            db,
            criador,
        )
    assert exc.value.status_code == 422
    await db.refresh(tarefa)
    assert tarefa.responsavel_id == criador.id


@pytest.mark.asyncio
async def test_patch_rejeita_cliente_externo_sem_mutar_tarefa(db):
    criador = _user(UserRole.advogado)
    externo = _user(UserRole.cliente_externo)
    tarefa = Task(
        id=str(uuid4()),
        titulo="Original",
        responsavel_id=criador.id,
        criado_por=criador.id,
    )
    db.add_all([criador, externo, tarefa])
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await tasks_router.atualizar(
            tarefa.id,
            tasks_router.TaskPatch(responsavel_id=externo.id),
            db,
            criador,
        )
    assert exc.value.status_code == 422
    await db.refresh(tarefa)
    assert tarefa.responsavel_id == criador.id
