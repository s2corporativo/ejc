"""Adaptadores v4 gravam apenas nas estruturas canônicas.

Executado após `alembic upgrade head`, portanto também valida que os campos de
compatibilidade da migration 110 existem e são mapeados pelo ORM.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import Response
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _fixtures(db):
    user_id = str(uuid4())
    client_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Compat V4', 'advogado', true)"
        ),
        {"id": user_id, "email": f"compat-v4-{user_id[:8]}@teste.local"},
    )
    await db.execute(
        text(
            "INSERT INTO clients (id, tipo, nome, email, status) "
            "VALUES (:id, 'PF', 'Cliente Compat V4', :email, 'ativo')"
        ),
        {"id": client_id, "email": f"client-v4-{client_id[:8]}@teste.local"},
    )
    await db.commit()

    from app.models.user import User

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    return user, user_id, client_id


async def _cleanup(db, *, room_ids=(), tese_ids=(), user_id: str, client_id: str):
    for room_id in room_ids:
        await db.execute(
            text("DELETE FROM data_room_acesso_logs WHERE link_id IN "
                 "(SELECT id FROM data_room_links WHERE data_room_id=:id)"),
            {"id": room_id},
        )
        await db.execute(text("DELETE FROM data_room_links WHERE data_room_id=:id"), {"id": room_id})
        await db.execute(text("DELETE FROM data_room_arquivos WHERE data_room_id=:id"), {"id": room_id})
        await db.execute(text("DELETE FROM data_rooms WHERE id=:id"), {"id": room_id})
        await db.execute(text("DELETE FROM dataroom_salas WHERE id=:id"), {"id": room_id})
    for tese_id in tese_ids:
        await db.execute(text("DELETE FROM tese_caso_links WHERE tese_id=:id"), {"id": tese_id})
        await db.execute(text("DELETE FROM teses WHERE id=:id"), {"id": tese_id})
        await db.execute(text("DELETE FROM teses_juridicas_v4 WHERE id=:id"), {"id": tese_id})
    await db.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
    await db.execute(text("DELETE FROM clients WHERE id=:id"), {"id": client_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def test_rotas_v4_persistem_somente_nas_tabelas_canonicas():
    from app.core.database import AsyncSessionLocal
    from app.models.data_room import DataRoom
    from app.models.tese import Tese
    from app.routers.data_room_v4 import SalaCreate, criar_sala
    from app.routers.teses_v4 import TeseCreate, criar_tese

    async with AsyncSessionLocal() as db:
        user, user_id, client_id = await _fixtures(db)
        room_id = tese_id = None
        try:
            room_response = Response()
            room = await criar_sala(
                SalaCreate(
                    nome="Sala canônica via v4",
                    descricao="Compatibilidade",
                    client_id=client_id,
                    expira_dias=10,
                ),
                room_response,
                db,
                user,
            )
            room_id = room["id"]
            assert room_response.headers["deprecation"] == "true"

            tese_response = Response()
            tese = await criar_tese(
                TeseCreate(
                    titulo="Tese criada pela compatibilidade v4",
                    descricao="Descrição histórica da tese",
                    fundamentacao="Fundamentação jurídica",
                    area_juridica="civil",
                ),
                tese_response,
                db,
                user,
            )
            tese_id = tese["id"]
            assert tese_response.headers["deprecation"] == "true"

            canonical_room = (
                await db.execute(select(DataRoom).where(DataRoom.id == room_id))
            ).scalar_one()
            canonical_tese = (
                await db.execute(select(Tese).where(Tese.id == tese_id))
            ).scalar_one()

            assert canonical_room.client_id == client_id
            assert canonical_room.legacy_expira_em is not None
            assert canonical_room.legacy_publica is False
            assert canonical_tese.legacy_vencedora is False
            assert canonical_tese.vezes_usada == 0
            assert canonical_tese.vezes_venceu == 0
            assert canonical_tese.taxa_sucesso == 0.0

            legacy_room_count = (
                await db.execute(
                    text("SELECT count(*) FROM dataroom_salas WHERE id=:id"),
                    {"id": room_id},
                )
            ).scalar_one()
            legacy_tese_count = (
                await db.execute(
                    text("SELECT count(*) FROM teses_juridicas_v4 WHERE id=:id"),
                    {"id": tese_id},
                )
            ).scalar_one()
            assert legacy_room_count == 0
            assert legacy_tese_count == 0
        finally:
            await _cleanup(
                db,
                room_ids=[room_id] if room_id else [],
                tese_ids=[tese_id] if tese_id else [],
                user_id=user_id,
                client_id=client_id,
            )


async def test_listagens_v4_preservam_expiracao_e_marcador_vencedora():
    from app.core.database import AsyncSessionLocal
    from app.models.data_room import DataRoom
    from app.models.tese import Tese, TeseStatus, TeseTipo
    from app.routers.data_room_v4 import listar_salas
    from app.routers.teses_v4 import listar_teses

    async with AsyncSessionLocal() as db:
        user, user_id, client_id = await _fixtures(db)
        room_id = str(uuid4())
        tese_id = str(uuid4())
        try:
            from datetime import datetime, timedelta, timezone

            expiry = datetime.now(timezone.utc) + timedelta(days=5)
            db.add(
                DataRoom(
                    id=room_id,
                    nome="Sala histórica consolidada",
                    client_id=client_id,
                    created_by=user_id,
                    legacy_expira_em=expiry,
                    legacy_publica=True,
                )
            )
            db.add(
                Tese(
                    id=tese_id,
                    titulo="Tese historicamente vencedora",
                    descricao="Registro consolidado",
                    fundamentacao="Fundamento",
                    area_juridica="civil",
                    tipo=TeseTipo.escritorio,
                    status=TeseStatus.ativa,
                    vezes_usada=0,
                    vezes_venceu=0,
                    vezes_perdeu=0,
                    taxa_sucesso=0.82,
                    legacy_vencedora=True,
                    created_by=user_id,
                )
            )
            await db.commit()

            room_response = Response()
            rooms = await listar_salas(room_response, db, user)
            listed_room = next(item for item in rooms if item["id"] == room_id)
            assert listed_room["expira_em"] == expiry

            tese_response = Response()
            teses = await listar_teses(tese_response, "civil", True, db, user)
            listed_tese = next(item for item in teses if item["id"] == tese_id)
            assert listed_tese["vencedora"] is True
            assert listed_tese["taxa_sucesso"] == pytest.approx(0.82)
        finally:
            await _cleanup(
                db,
                room_ids=[room_id],
                tese_ids=[tese_id],
                user_id=user_id,
                client_id=client_id,
            )
