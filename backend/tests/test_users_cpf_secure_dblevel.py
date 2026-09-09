from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


def _cpf_teste_valido() -> str:
    base = [1, 5, 3, 5, 0, 9, 4, 6, 0]
    soma1 = sum(n * p for n, p in zip(base, range(10, 1, -1)))
    d1 = 0 if (11 - soma1 % 11) >= 10 else (11 - soma1 % 11)
    dez = base + [d1]
    soma2 = sum(n * p for n, p in zip(dez, range(11, 1, -1)))
    d2 = 0 if (11 - soma2 % 11) >= 10 else (11 - soma2 % 11)
    return "".join(str(n) for n in dez + [d2])


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    from app.core.database import engine
    await engine.dispose()
    yield
    await engine.dispose()


async def test_usuario_cpf_persiste_so_cipher_hash_e_mascara():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User, UserRole
    from app.services.pii_crypto import encrypt, hash_documento, mascarar_documento

    uid = str(uuid4())
    cpf = _cpf_teste_valido()
    async with AsyncSessionLocal() as db:
        u = User(
            id=uid,
            email=f"{uid[:8]}@teste.local",
            hashed_password="x",
            full_name="Sócio Teste",
            role=UserRole.socio,
            cpf_enc=encrypt(cpf),
            cpf_hash=hash_documento(cpf),
            is_active=True,
        )
        db.add(u)
        await db.commit()
        try:
            row = (await db.execute(
                text("SELECT cpf_enc, cpf_hash FROM users WHERE id=:id"), {"id": uid}
            )).mappings().one()
            assert row["cpf_enc"] != cpf
            assert row["cpf_hash"] == hash_documento(cpf)
            await db.refresh(u)
            assert u.cpf_mascarado == mascarar_documento(cpf)
            cols = (await db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='users' AND column_name='cpf'"
            ))).scalars().all()
            assert cols == []
        finally:
            await db.execute(text("DELETE FROM users WHERE id=:id"), {"id": uid})
            await db.commit()


async def test_cpf_duplicado_entre_usuarios_ativos_e_bloqueado_no_banco():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User, UserRole
    from app.services.pii_crypto import encrypt, hash_documento

    cpf = _cpf_teste_valido()
    ids = [str(uuid4()), str(uuid4())]
    async with AsyncSessionLocal() as db:
        try:
            for idx, uid in enumerate(ids):
                db.add(User(
                    id=uid,
                    email=f"{uid[:8]}@teste.local",
                    hashed_password="x",
                    full_name=f"Sócio {idx}",
                    role=UserRole.socio,
                    cpf_enc=encrypt(cpf),
                    cpf_hash=hash_documento(cpf),
                    is_active=True,
                ))
                if idx == 0:
                    await db.commit()
                else:
                    with pytest.raises(IntegrityError):
                        await db.commit()
                    await db.rollback()
        finally:
            for uid in ids:
                await db.execute(text("DELETE FROM users WHERE id=:id"), {"id": uid})
            await db.commit()
