"""Access token emitido antes da troca de senha deixa de valer (migr. 128).

Trocar a senha já revogava todos os `refresh_tokens`, mas o ACCESS token é
auto-contido e validado só por assinatura: continuava aceito até o seu `exp`
(`ACCESS_TOKEN_EXPIRE_HOURS`). Quem trocava a senha por suspeita de
comprometimento seguia comprometido pelas horas seguintes — exatamente a janela
em que a troca deveria produzir efeito.

Nível de banco porque a checagem depende do valor PERSISTIDO em
`users.password_changed_at`, que `get_current_user` lê a cada requisição.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_usuario(db) -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, "
            "is_active) VALUES (:id, :email, 'x', 'Adv Teste', 'advogado', true)"
        ),
        {"id": uid, "email": f"tok-{uid[:8]}@senha.local"},
    )
    return uid


async def _marcar_troca_de_senha(db, uid: str, quando: datetime) -> None:
    await db.execute(
        text("UPDATE users SET password_changed_at = :q WHERE id = :id"),
        {"q": quando, "id": uid},
    )


async def _limpar(db, uid: str) -> None:
    await db.execute(text("DELETE FROM refresh_tokens WHERE user_id = :id"), {"id": uid})
    await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
    await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def _autenticar(db, token: str):
    from app.core.security import get_current_user

    return await get_current_user(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
        db=db,
    )


async def test_token_anterior_a_troca_de_senha_e_recusado():
    """O caso que dá nome ao defeito: token roubado antes da troca não pode
    continuar abrindo a API depois dela."""
    from app.core.database import AsyncSessionLocal
    from app.core.security import create_access_token

    async with AsyncSessionLocal() as db:
        uid = await _criar_usuario(db)
        await db.commit()
        try:
            token_antigo = create_access_token(uid, "advogado")
            # Token vale ANTES da troca.
            assert (await _autenticar(db, token_antigo)).id == uid

            # Troca ocorre depois da emissão.
            await _marcar_troca_de_senha(
                db, uid, datetime.now(timezone.utc) + timedelta(seconds=5)
            )
            await db.commit()
            db.expire_all()

            with pytest.raises(HTTPException) as exc:
                await _autenticar(db, token_antigo)
            assert exc.value.status_code == 401
        finally:
            await _limpar(db, uid)


async def test_token_emitido_apos_a_troca_continua_valendo():
    """A trava não pode derrubar a sessão nova: quem acabou de trocar a senha
    recebe um access token na própria resposta e precisa seguir logado."""
    from app.core.database import AsyncSessionLocal
    from app.core.security import create_access_token

    async with AsyncSessionLocal() as db:
        uid = await _criar_usuario(db)
        await db.commit()
        try:
            await _marcar_troca_de_senha(
                db, uid, datetime.now(timezone.utc) - timedelta(minutes=5)
            )
            await db.commit()
            db.expire_all()
            assert (await _autenticar(db, create_access_token(uid, "advogado"))).id == uid
        finally:
            await _limpar(db, uid)


async def test_troca_no_mesmo_segundo_da_emissao_nao_invalida_o_token_novo():
    """`iat` do JWT é inteiro em SEGUNDOS. Se a marca fosse gravada com
    microssegundos, o access emitido no fim da própria troca teria `iat` menor
    que ela e nasceria inválido — o usuário trocaria a senha e cairia para fora.
    Por isso a aplicação trunca ao segundo; aqui provamos o efeito."""
    from app.core.database import AsyncSessionLocal
    from app.core.security import create_access_token

    async with AsyncSessionLocal() as db:
        uid = await _criar_usuario(db)
        await db.commit()
        try:
            agora = datetime.now(timezone.utc)
            await _marcar_troca_de_senha(db, uid, agora.replace(microsecond=0))
            await db.commit()
            db.expire_all()
            assert (await _autenticar(db, create_access_token(uid, "advogado"))).id == uid
        finally:
            await _limpar(db, uid)


async def test_usuario_sem_marca_nao_tem_sessao_derrubada():
    """`NULL` = senha nunca redefinida desde a migration. A coluna nasce sem
    backfill justamente para o deploy não deslogar o escritório inteiro."""
    from app.core.database import AsyncSessionLocal
    from app.core.security import create_access_token

    async with AsyncSessionLocal() as db:
        uid = await _criar_usuario(db)
        await db.commit()
        try:
            assert (await _autenticar(db, create_access_token(uid, "advogado"))).id == uid
        finally:
            await _limpar(db, uid)
