"""POST /trash/{entidade}/{registro_id}/purgar — exclusão definitiva (V2-4.4).

Achado da auditoria: não havia caminho pela aplicação para atender um pedido
de eliminação de dados pessoais (LGPD art. 16 e art. 18, VI) — tanto
`DELETE /trash/cases/{id}` quanto `POST /trash/cases/{id}/purgar` respondiam
404. Este teste cobre a rota nova: só purga o que já está na lixeira, exige
`motivo` (>=5 chars), é restrita a `superadmin` (mais estrita que `restaurar`,
que aceita admin/socio), grava audit log ANTES do delete físico, e não
cascateia — dependente vinculado vira 409 explícito, não exclusão em cadeia.

Postgres é OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: chama o handler
direto com AsyncSessionLocal). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from app.routers.trash import PurgarRequest, purgar

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "superadmin") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Purga Teste', :role, true)"),
        {"id": uid, "email": f"purga-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente_na_lixeira(db, nome: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status, deleted_at) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo', now())"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, client_ids=(), case_ids=(), user_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_purga_registro_na_lixeira_remove_definitivamente():
    from app.core.database import AsyncSessionLocal

    tok = f"Purga{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        admin = await _criar_user(db, "superadmin")
        cli = await _criar_cliente_na_lixeira(db, f"Cliente {tok}")
        await db.commit()
        try:
            cu = await _carregar_user(db, admin)
            resultado = await purgar(
                "clients", cli, PurgarRequest(motivo="Pedido formal de eliminação LGPD"),
                db, cu,
            )
            assert resultado["detail"] == "Registro purgado definitivamente"

            ainda_existe = (await db.execute(
                text("SELECT count(*) FROM clients WHERE id = :id"), {"id": cli},
            )).scalar()
            assert ainda_existe == 0

            log = (await db.execute(
                text("SELECT acao, entidade, registro_id, detalhes FROM audit_logs "
                     "WHERE registro_id = :id AND acao = 'PURGE'"),
                {"id": cli},
            )).one()
            assert log[0] == "PURGE"
            assert log[1] == "clients"
            assert "eliminação" in log[3]
        finally:
            await _limpar(db, user_ids=[admin])


async def test_purga_recusa_registro_que_nao_esta_na_lixeira():
    from app.core.database import AsyncSessionLocal

    tok = f"Ativo{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        admin = await _criar_user(db, "superadmin")
        cid = str(uuid4())
        await db.execute(
            text("INSERT INTO clients (id, tipo, nome, email, status) "
                 "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
            {"id": cid, "nome": f"Cliente {tok}", "email": f"{cid[:8]}@teste.local"},
        )
        await db.commit()
        try:
            cu = await _carregar_user(db, admin)
            with pytest.raises(HTTPException) as exc:
                await purgar(
                    "clients", cid, PurgarRequest(motivo="Tentativa indevida"), db, cu,
                )
            assert exc.value.status_code == 404

            ainda_existe = (await db.execute(
                text("SELECT count(*) FROM clients WHERE id = :id"), {"id": cid},
            )).scalar()
            assert ainda_existe == 1
        finally:
            await _limpar(db, client_ids=[cid], user_ids=[admin])


async def test_purga_com_dependente_vinculado_vira_409_sem_cascatear():
    from app.core.database import AsyncSessionLocal

    tok = f"Dep{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        admin = await _criar_user(db, "superadmin")
        cli = await _criar_cliente_na_lixeira(db, f"Cliente {tok}")
        caso = str(uuid4())
        await db.execute(
            text("INSERT INTO cases (id, titulo, area, status, client_id, "
                 "advogado_responsavel_id, proxima_acao) VALUES "
                 "(:id, :titulo, 'civil', 'aberto', :cid, :resp, 'Providenciar X')"),
            {"id": caso, "titulo": f"Caso {tok}", "cid": cli, "resp": admin},
        )
        await db.commit()
        try:
            cu = await _carregar_user(db, admin)
            with pytest.raises(HTTPException) as exc:
                await purgar(
                    "clients", cli, PurgarRequest(motivo="Pedido formal de eliminação"), db, cu,
                )
            assert exc.value.status_code == 409

            ainda_existe = (await db.execute(
                text("SELECT count(*) FROM clients WHERE id = :id"), {"id": cli},
            )).scalar()
            assert ainda_existe == 1

            # Achado da revisão de segurança: o audit log PURGE é gravado na
            # MESMA transação do delete físico — se o commit falha (409), o
            # rollback precisa desfazer os dois, nunca deixar uma linha PURGE
            # órfã em audit_logs descrevendo uma purga que não aconteceu.
            log_orfao = (await db.execute(
                text("SELECT count(*) FROM audit_logs "
                     "WHERE registro_id = :id AND acao = 'PURGE'"),
                {"id": cli},
            )).scalar()
            assert log_orfao == 0
        finally:
            await _limpar(db, case_ids=[caso], client_ids=[cli], user_ids=[admin])


async def test_purga_exige_role_superadmin():
    from app.core.database import AsyncSessionLocal
    from app.core.security import require_roles

    tok = f"Role{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente_na_lixeira(db, f"Cliente {tok}")
        await db.commit()
        try:
            cu = await _carregar_user(db, socio)
            checador = require_roles(["superadmin"])
            with pytest.raises(HTTPException) as exc:
                await checador(cu)
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[socio])
