"""PATCH /cases/{case_id} — gate de papel para `sigilo_reforcado`.

Achado do `security-auditor` (Issue #1194, item 3): `sigilo_reforcado` é o
único mecanismo que faz o piso LOCAL_COMPLETO de IA (crimes sexuais/menores)
alcançar um caso real (`orchestrator.py`/`agent/loop.py` consultam esse campo
com prioridade sobre a área). O frontend restringe a edição do checkbox a
`superadmin/admin/socio/advogado` (`TabResumo.tsx`), mas o PATCH genérico
aceitava a mudança de QUALQUER usuário com visibilidade sobre o caso — um
`advogado_auxiliar` (coadjuvante, com acesso legítimo ao caso via
`_filtro_visibilidade`) conseguia desmarcar a flag de um caso de crime
sexual/menor chamando a API direto, sem passar pela UI.

Postgres é OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: chama o handler
direto com AsyncSessionLocal). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from starlette.background import BackgroundTasks

from app.schemas.case import CaseUpdate

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str) -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Gate Sigilo Teste', :role, true)"),
        {"id": uid, "email": f"gate-sigilo-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db, nome: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(db, client_id: str, titulo: str, *, resp_id: str | None = None,
                       aux_id: str | None = None, sigilo: bool = False) -> str:
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id, "
            "advogado_responsavel_id, advogado_auxiliar_id, proxima_acao, sigilo_reforcado) "
            "VALUES (:id, :titulo, 'civil', 'em_instrucao', :cid, :resp, :aux, "
            "'Providenciar X', :sigilo)"
        ),
        {"id": case_id, "titulo": titulo, "cid": client_id,
         "resp": resp_id, "aux": aux_id, "sigilo": sigilo},
    )
    return case_id


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_advogado_auxiliar_nao_pode_ligar_sigilo_reforcado():
    """Coadjuvante do caso (acesso legítimo via _filtro_visibilidade) não tem
    papel suficiente para MUDAR o sigilo reforçado."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import atualizar

    tok = f"SigAux{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        aux = await _criar_user(db, "advogado_auxiliar")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=socio, aux_id=aux)
        await db.commit()
        try:
            cu = await _carregar_user(db, aux)
            with pytest.raises(HTTPException) as exc:
                await atualizar(
                    caso, CaseUpdate(sigilo_reforcado=True), BackgroundTasks(),
                    db, cu,
                )
            assert exc.value.status_code == 403
            assert "sigilo" in str(exc.value.detail).lower()

            valor = (await db.execute(
                text("SELECT sigilo_reforcado FROM cases WHERE id = :id"), {"id": caso},
            )).scalar()
            assert valor is False
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[socio, aux], client_ids=[cli])


async def test_advogado_auxiliar_nao_pode_desligar_sigilo_reforcado():
    """Mesma trava no sentido inverso: desmarcar um caso já sinalizado exige
    o mesmo papel — o achado do security-auditor era exatamente sobre alguém
    REBAIXAR a proteção de um caso sensível."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import atualizar

    tok = f"SigAuxOff{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        aux = await _criar_user(db, "advogado_auxiliar")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=socio, aux_id=aux, sigilo=True)
        await db.commit()
        try:
            cu = await _carregar_user(db, aux)
            with pytest.raises(HTTPException) as exc:
                await atualizar(
                    caso, CaseUpdate(sigilo_reforcado=False), BackgroundTasks(),
                    db, cu,
                )
            assert exc.value.status_code == 403

            valor = (await db.execute(
                text("SELECT sigilo_reforcado FROM cases WHERE id = :id"), {"id": caso},
            )).scalar()
            assert valor is True
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[socio, aux], client_ids=[cli])


async def test_advogado_auxiliar_pode_atualizar_outros_campos_sem_mexer_no_sigilo():
    """O gate é ESPECÍFICO de `sigilo_reforcado` — o resto do PATCH continua
    livre para quem já tem visibilidade sobre o caso."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import atualizar

    tok = f"SigAuxOk{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        aux = await _criar_user(db, "advogado_auxiliar")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=socio, aux_id=aux)
        await db.commit()
        try:
            cu = await _carregar_user(db, aux)
            await atualizar(
                caso, CaseUpdate(prioridade="alta"), BackgroundTasks(), db, cu,
            )
            row = (await db.execute(
                text("SELECT prioridade, sigilo_reforcado FROM cases WHERE id = :id"),
                {"id": caso},
            )).one()
            assert row[0] == "alta"
            assert row[1] is False
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[socio, aux], client_ids=[cli])


async def test_reenvio_do_mesmo_valor_nao_exige_papel_especial():
    """Reenviar o MESMO valor (payload "salvar tudo" que reenvia o objeto
    inteiro) não é uma mudança de sigilo — não pode 403 quem nem estava
    tentando alterar o campo."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import atualizar

    tok = f"SigReenv{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        aux = await _criar_user(db, "advogado_auxiliar")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=socio, aux_id=aux, sigilo=False)
        await db.commit()
        try:
            cu = await _carregar_user(db, aux)
            await atualizar(
                caso, CaseUpdate(sigilo_reforcado=False, prioridade="alta"),
                BackgroundTasks(), db, cu,
            )
            row = (await db.execute(
                text("SELECT prioridade, sigilo_reforcado FROM cases WHERE id = :id"),
                {"id": caso},
            )).one()
            assert row[0] == "alta"
            assert row[1] is False
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[socio, aux], client_ids=[cli])


async def test_advogado_responsavel_pode_ligar_sigilo_reforcado():
    """Papel suficiente (advogado, dono do caso) — caminho feliz."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import atualizar

    tok = f"SigAdv{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=adv)
        await db.commit()
        try:
            cu = await _carregar_user(db, adv)
            await atualizar(
                caso, CaseUpdate(sigilo_reforcado=True), BackgroundTasks(), db, cu,
            )
            valor = (await db.execute(
                text("SELECT sigilo_reforcado FROM cases WHERE id = :id"), {"id": caso},
            )).scalar()
            assert valor is True
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[adv], client_ids=[cli])


async def test_socio_pode_desligar_sigilo_reforcado():
    """Gestão (sócio+) sempre passa — mesmo padrão de _filtro_visibilidade."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import atualizar

    tok = f"SigSocio{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=adv, sigilo=True)
        await db.commit()
        try:
            cu = await _carregar_user(db, socio)
            await atualizar(
                caso, CaseUpdate(sigilo_reforcado=False), BackgroundTasks(), db, cu,
            )
            valor = (await db.execute(
                text("SELECT sigilo_reforcado FROM cases WHERE id = :id"), {"id": caso},
            )).scalar()
            assert valor is False
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[adv, socio], client_ids=[cli])
