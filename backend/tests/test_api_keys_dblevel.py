from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _criar_admin(db) -> SimpleNamespace:
    """`require_admin` já foi satisfeito pela dependency; o router só usa
    `cu.id` e `cu.role` para o audit log. O `id` precisa existir em `users`
    (FK real de audit_logs)."""
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Admin Teste Chaves', 'admin', true)"
        ),
        {"id": uid, "email": f"adm-{uid[:8]}@teste.local"},
    )
    await db.commit()
    return SimpleNamespace(id=uid, role="admin")


async def _limpar(db, key_ids=(), user_ids=()):
    for kid in key_ids:
        # trigger WORM exige a flag LOCAL na mesma transação
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE registro_id = :id"), {"id": kid})
        await db.execute(text("DELETE FROM api_keys WHERE id = :id"), {"id": kid})
    for uid in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


class _RequestFake:
    """`require_api_key` consome cota por IP antes do lookup (anti-brute-force)."""
    client = SimpleNamespace(host="203.0.113.7")
    headers: dict = {}


async def test_chave_em_claro_nunca_chega_ao_banco():
    """A promessa central do módulo. O teste varre TODAS as colunas de texto da
    linha gravada procurando o segredo — não só as que eu esperaria."""
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        resp = await criar_api_key(
            ApiKeyCreate(nome="n8n de teste", escopo="knowledge:write"), db, admin
        )
        chave, key_id = resp["chave"], resp["id"]
        try:
            linha = (await db.execute(
                text("SELECT * FROM api_keys WHERE id = :id"), {"id": key_id}
            )).mappings().first()
            textos = [str(v) for v in linha.values() if v is not None]
            # Sem esta linha o teste seria VACUAMENTE verdadeiro caso a varredura
            # devolvesse nada — `all()` sobre lista vazia passa. É a diferença
            # entre "não achei o segredo" e "não procurei".
            assert len(textos) >= 6, f"a varredura não leu a linha: {textos}"
            assert all(chave not in t for t in textos), (
                "a chave em claro foi persistida em alguma coluna de api_keys"
            )

            # O que existe no banco é o SHA-256 dela — e nada mais.
            from app.core.api_key_auth import hash_chave
            assert linha["chave_hash"] == hash_chave(chave)
            # O prefixo identifica a chave sem revelá-la: 12 de ~47 caracteres.
            assert chave.startswith(linha["prefixo"])
            assert len(linha["prefixo"]) < len(chave) / 3
        finally:
            await _limpar(db, [key_id], [admin.id])


async def test_segredo_aparece_uma_unica_vez_e_some_da_listagem():
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key, listar_api_keys

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        resp = await criar_api_key(ApiKeyCreate(nome="chave unica"), db, admin)
        chave, key_id = resp["chave"], resp["id"]
        try:
            assert resp["aviso"]  # o texto avisa que não se repete

            listagem = await listar_api_keys(db, admin)
            minha = next(k for k in listagem["data"] if k["id"] == key_id)
            assert "chave" not in minha
            assert chave not in str(listagem)
            assert minha["prefixo"] == resp["prefixo"]
        finally:
            await _limpar(db, [key_id], [admin.id])


async def test_chave_recem_criada_autentica_e_carrega_o_escopo():
    """O caminho feliz — sem ele, os testes de negação abaixo provariam apenas
    que TUDO é recusado."""
    from app.core.api_key_auth import require_api_key
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        resp = await criar_api_key(ApiKeyCreate(nome="chave viva"), db, admin)
        chave, key_id = resp["chave"], resp["id"]
        try:
            dep = require_api_key("knowledge:write")
            ak = await dep(_RequestFake(), chave, db)
            assert ak.id == key_id
            # `last_used_at` passa a existir — é o que detecta chave órfã.
            assert ak.last_used_at is not None
        finally:
            await _limpar(db, [key_id], [admin.id])


async def test_revogar_bloqueia_a_chave_de_verdade_e_preserva_a_linha():
    """Revogação não é cosmética: a MESMA chave que autenticava tem de passar a
    receber 401 na requisição seguinte. E a linha fica — auditoria não se apaga.
    """
    from app.core.api_key_auth import require_api_key
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key, revogar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        resp = await criar_api_key(ApiKeyCreate(nome="chave a revogar"), db, admin)
        chave, key_id = resp["chave"], resp["id"]
        dep = require_api_key("knowledge:write")
        try:
            assert (await dep(_RequestFake(), chave, db)).id == key_id   # antes: passa

            await revogar_api_key(key_id, db, admin)

            with pytest.raises(HTTPException) as exc:                    # depois: 401
                await dep(_RequestFake(), chave, db)
            assert exc.value.status_code == 401

            linha = (await db.execute(
                text("SELECT ativo, revoked_at FROM api_keys WHERE id = :id"),
                {"id": key_id},
            )).mappings().first()
            assert linha is not None, "a linha foi APAGADA — perde-se a auditoria"
            assert linha["ativo"] is False and linha["revoked_at"] is not None
        finally:
            await _limpar(db, [key_id], [admin.id])


async def test_revogar_duas_vezes_e_idempotente():
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key, revogar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        key_id = (await criar_api_key(ApiKeyCreate(nome="dupla revogacao"), db, admin))["id"]
        try:
            primeira = await revogar_api_key(key_id, db, admin)
            segunda = await revogar_api_key(key_id, db, admin)
            assert "revogada" in primeira["detail"]
            assert "já estava revogada" in segunda["detail"]
            # A data da primeira revogação não é reescrita pela segunda.
            assert primeira["revoked_at"] == segunda["revoked_at"]
        finally:
            await _limpar(db, [key_id], [admin.id])


async def test_revogar_chave_inexistente_responde_404():
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import revogar_api_key

I will now create the helper file and update multiple test files as authorized. I'll commit the changes to the branch fix/ci-auditlogs-alembic and open a PR. Proceeding to add the helper and modify tests now. (I will run the file create/update calls.)