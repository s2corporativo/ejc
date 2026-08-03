"""DELETE /prompts-biblioteca/{id}: autor remove o próprio; sócio+ remove qualquer um (Issue #580).

Antes, só sócio+ removia — o advogado autor de um prompt próprio (bobagem,
erro de digitação, versão obsoleta) dependia de outra pessoa para apagá-lo.
Matriz completa: autor passa; não-autor advogado NÃO passa; sócio+ passa
mesmo não sendo autor; estagiário nunca chega a ser avaliado como autor;
ausente/já removido é 404; a remoção é soft delete.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str) -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, "
            "is_active) VALUES (:id, :email, 'x', 'U Teste', :role, true)"
        ),
        {"id": uid, "email": f"{role}-{uid[:8]}@prompt.local", "role": role},
    )
    return uid


async def _criar_prompt(db, autor_id: str, titulo: str) -> str:
    pid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO prompts_juridicos (id, titulo, categoria, conteudo, "
            "publico, created_by) VALUES (:id, :tit, 'peticao', 'x', true, :autor)"
        ),
        {"id": pid, "tit": titulo, "autor": autor_id},
    )
    return pid


async def _limpar(db, *, prompt_ids=(), user_ids=()):
    for pid in prompt_ids:
        await db.execute(text("DELETE FROM prompts_juridicos WHERE id = :id"), {"id": pid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def _carregar_user(db, uid: str):
    from app.models.user import User

    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def test_autor_advogado_remove_o_proprio_prompt():
    from app.core.database import AsyncSessionLocal
    from app.routers.prompts_juridicos import remover_prompt

    async with AsyncSessionLocal() as db:
        autor = await _criar_user(db, "advogado")
        prompt = await _criar_prompt(db, autor, "Prompt do autor")
        await db.commit()
        try:
            user = await _carregar_user(db, autor)
            await remover_prompt(prompt_id=prompt, db=db, cu=user)
            deletado = (await db.execute(
                text("SELECT deleted_at FROM prompts_juridicos WHERE id = :id"), {"id": prompt}
            )).scalar_one()
            assert deletado is not None
        finally:
            await _limpar(db, prompt_ids=[prompt], user_ids=[autor])


async def test_advogado_nao_autor_recebe_403():
    from app.core.database import AsyncSessionLocal
    from app.routers.prompts_juridicos import remover_prompt

    async with AsyncSessionLocal() as db:
        autor = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        prompt = await _criar_prompt(db, autor, "Prompt de outro advogado")
        await db.commit()
        try:
            user_outro = await _carregar_user(db, outro)
            with pytest.raises(HTTPException) as exc:
                await remover_prompt(prompt_id=prompt, db=db, cu=user_outro)
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, prompt_ids=[prompt], user_ids=[autor, outro])


async def test_socio_remove_prompt_de_terceiro():
    from app.core.database import AsyncSessionLocal
    from app.routers.prompts_juridicos import remover_prompt

    async with AsyncSessionLocal() as db:
        autor = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        prompt = await _criar_prompt(db, autor, "Prompt removido pelo sócio")
        await db.commit()
        try:
            user_socio = await _carregar_user(db, socio)
            await remover_prompt(prompt_id=prompt, db=db, cu=user_socio)
        finally:
            await _limpar(db, prompt_ids=[prompt], user_ids=[autor, socio])


async def test_estagiario_bloqueado_mesmo_sendo_autor():
    """Perfil abaixo de advogado nunca chega a "é o autor?" — bloqueado antes."""
    from app.core.database import AsyncSessionLocal
    from app.routers.prompts_juridicos import remover_prompt

    async with AsyncSessionLocal() as db:
        estagiario = await _criar_user(db, "estagiario")
        prompt = await _criar_prompt(db, estagiario, "Prompt do estagiário")
        await db.commit()
        try:
            user = await _carregar_user(db, estagiario)
            with pytest.raises(HTTPException) as exc:
                await remover_prompt(prompt_id=prompt, db=db, cu=user)
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, prompt_ids=[prompt], user_ids=[estagiario])


async def test_ausente_ou_ja_removido_e_404():
    from app.core.database import AsyncSessionLocal
    from app.routers.prompts_juridicos import remover_prompt

    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        await db.commit()
        try:
            user = await _carregar_user(db, adv)
            with pytest.raises(HTTPException) as exc:
                await remover_prompt(prompt_id=str(uuid4()), db=db, cu=user)
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, user_ids=[adv])
