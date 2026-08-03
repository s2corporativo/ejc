"""DELETE /checklists/templates/{id}: autor remove o próprio; sócio+ remove qualquer um (Issue #578).

Mesma matriz de #580, aplicada a `ChecklistTemplate`: autor advogado remove o
próprio; advogado não autor recebe 403; sócio+ remove de outro autor;
estagiário continua bloqueado; ausente/já removido é 404; nenhum registro é
apagado fisicamente (soft delete).
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

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
        {"id": uid, "email": f"{role}-{uid[:8]}@checklist.local", "role": role},
    )
    return uid


async def _criar_template(db, autor_id: str, nome: str) -> str:
    tid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO checklist_templates (id, nome, created_by) "
            "VALUES (:id, :nome, :autor)"
        ),
        {"id": tid, "nome": nome, "autor": autor_id},
    )
    return tid


async def _limpar(db, *, template_ids=(), user_ids=()):
    for tid in template_ids:
        await db.execute(text("DELETE FROM checklist_template_items WHERE template_id = :id"), {"id": tid})
        await db.execute(text("DELETE FROM checklist_templates WHERE id = :id"), {"id": tid})
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
    from sqlalchemy import select

    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def test_autor_advogado_remove_o_proprio_template():
    from app.core.database import AsyncSessionLocal
    from app.routers.checklists import remover_template

    async with AsyncSessionLocal() as db:
        autor = await _criar_user(db, "advogado")
        tpl = await _criar_template(db, autor, "Template do autor")
        await db.commit()
        try:
            user = await _carregar_user(db, autor)
            await remover_template(template_id=tpl, db=db, cu=user)
            deletado = (await db.execute(
                text("SELECT deleted_at FROM checklist_templates WHERE id = :id"), {"id": tpl}
            )).scalar_one()
            assert deletado is not None
        finally:
            await _limpar(db, template_ids=[tpl], user_ids=[autor])


async def test_advogado_nao_autor_recebe_403():
    from app.core.database import AsyncSessionLocal
    from app.routers.checklists import remover_template

    async with AsyncSessionLocal() as db:
        autor = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        tpl = await _criar_template(db, autor, "Template de outro advogado")
        await db.commit()
        try:
            user_outro = await _carregar_user(db, outro)
            with pytest.raises(HTTPException) as exc:
                await remover_template(template_id=tpl, db=db, cu=user_outro)
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, template_ids=[tpl], user_ids=[autor, outro])


async def test_socio_remove_template_de_outro_autor():
    from app.core.database import AsyncSessionLocal
    from app.routers.checklists import remover_template

    async with AsyncSessionLocal() as db:
        autor = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        tpl = await _criar_template(db, autor, "Template removido pelo sócio")
        await db.commit()
        try:
            user_socio = await _carregar_user(db, socio)
            await remover_template(template_id=tpl, db=db, cu=user_socio)
        finally:
            await _limpar(db, template_ids=[tpl], user_ids=[autor, socio])


async def test_estagiario_continua_bloqueado():
    """Perfil abaixo de advogado nunca chega a "é o autor?" — bloqueado antes.
    Regressão específica: `checklists.py` tem `_pode_editar` (piso estagiário)
    E `_pode_gerenciar` (piso advogado) com nomes INVERTIDOS aos de
    prompts_juridicos.py — usar o helper errado deixaria estagiário passar."""
    from app.core.database import AsyncSessionLocal
    from app.routers.checklists import remover_template

    async with AsyncSessionLocal() as db:
        estagiario = await _criar_user(db, "estagiario")
        tpl = await _criar_template(db, estagiario, "Template do estagiário")
        await db.commit()
        try:
            user = await _carregar_user(db, estagiario)
            with pytest.raises(HTTPException) as exc:
                await remover_template(template_id=tpl, db=db, cu=user)
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, template_ids=[tpl], user_ids=[estagiario])


async def test_ausente_ou_ja_removido_e_404():
    from app.core.database import AsyncSessionLocal
    from app.routers.checklists import remover_template

    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        await db.commit()
        try:
            user = await _carregar_user(db, adv)
            with pytest.raises(HTTPException) as exc:
                await remover_template(template_id=str(uuid4()), db=db, cu=user)
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, user_ids=[adv])


async def test_remocao_e_soft_delete_nao_apaga_fisicamente():
    """Critério explícito da Issue: nenhum registro é apagado fisicamente."""
    from app.core.database import AsyncSessionLocal
    from app.routers.checklists import remover_template

    async with AsyncSessionLocal() as db:
        autor = await _criar_user(db, "advogado")
        tpl = await _criar_template(db, autor, "Template para conferir soft delete")
        await db.commit()
        try:
            user = await _carregar_user(db, autor)
            await remover_template(template_id=tpl, db=db, cu=user)
            ainda_existe = (await db.execute(
                text("SELECT count(*) FROM checklist_templates WHERE id = :id"), {"id": tpl}
            )).scalar_one()
            assert ainda_existe == 1
        finally:
            await _limpar(db, template_ids=[tpl], user_ids=[autor])
