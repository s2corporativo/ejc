# -*- coding: utf-8 -*-
"""Excluir caso leva junto a peça em curso (AUD27-P3-10 / V2-3.3).

O soft-delete do caso marcava só `cases.deleted_at`: a peça em rascunho
continuava com `deleted_at IS NULL`, viva no banco e órfã de um caso que já
não existe. Alguns endpoints filtravam pelo pai por conta própria (o detalhe
de peça devolvia 404), mas os que não filtravam seguiam contando a linha —
foi assim que AUD27-P2-1 apareceu no painel de guardrails.

A peça PROTOCOLADA não entra nesta cascata: ela bloqueia a exclusão antes
(422 com `pendencias`), e este teste trava esse contrato também.

Roda contra Postgres real (AsyncSessionLocal). Sem RUN_DB_TESTS=1, pula.
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


async def _criar_user(db, role: str = "socio") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Cascata Teste', :role, true)"),
        {"id": uid, "email": f"cascata-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": f"cascata-{cid[:8]}", "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(db, client_id: str, resp_id: str) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "advogado_responsavel_id, proxima_acao) VALUES "
             "(:id, :titulo, 'civil', 'em_instrucao', :cid, :resp, 'Providenciar X')"),
        {"id": case_id, "titulo": f"cascata-{case_id[:8]}", "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _criar_peca(db, case_id: str, status: str) -> str:
    # `status` é literal fixo do teste — inlinado como nos demais *_dblevel.py
    # (o enum pecastatus rejeita bind sem cast explícito).
    assert status in ("rascunho", "protocolada")
    doc_id = str(uuid4())
    await db.execute(
        text("INSERT INTO legal_docs (id, titulo, tipo_peca, conteudo, case_id, status) "
             f"VALUES (:id, :titulo, 'peticao_inicial', 'minuta', :cid, '{status}')"),
        {"id": doc_id, "titulo": f"cascata-peca-{doc_id[:8]}", "cid": case_id},
    )
    return doc_id


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _peca_excluida(db, doc_id: str) -> bool:
    valor = (await db.execute(
        text("SELECT deleted_at FROM legal_docs WHERE id = :i"), {"i": doc_id}
    )).scalar()
    return valor is not None


async def _limpar(db, *, case_id: str, client_id: str, user_id: str) -> None:
    """Remoção FÍSICA do que o teste criou (o endpoint faz soft-delete)."""
    # `audit_logs` é WORM (trigger bloqueia DELETE — Issue #582): a trilha do
    # teste fica, como manda o desenho. O resto sai.
    await db.execute(text("DELETE FROM legal_docs WHERE case_id = :c"), {"c": case_id})
    await db.execute(text("DELETE FROM cases WHERE id = :c"), {"c": case_id})
    await db.execute(text("DELETE FROM clients WHERE id = :c"), {"c": client_id})
    # O usuário é referenciado pela trilha WORM (FK audit_logs.user_id), então
    # não pode ser apagado — sai desativado, que é o que a própria aplicação faz.
    await db.execute(
        text("UPDATE users SET is_active = false, deleted_at = now() WHERE id = :u"),
        {"u": user_id},
    )
    await db.commit()


@pytest.mark.asyncio
async def test_excluir_caso_cascateia_peca_em_curso():
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import excluir

    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db)
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, socio)
        peca = await _criar_peca(db, caso, "rascunho")
        await db.commit()
        try:
            assert not await _peca_excluida(db, peca)

            await excluir(
                caso, motivo="exclusao de teste da cascata", payload=None,
                db=db, cu=await _carregar_user(db, socio),
            )

            assert await _peca_excluida(db, peca), (
                "peça em rascunho ficou órfã: caso excluído, peça viva no banco "
                "— é o que fazia contadores somarem trabalho inexistente"
            )
        finally:
            await _limpar(db, case_id=caso, client_id=cli, user_id=socio)


@pytest.mark.asyncio
async def test_peca_protocolada_bloqueia_a_exclusao_em_vez_de_cascatear():
    """Contrato inverso: o que é terminal não some junto — barra a exclusão."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import excluir

    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db)
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, socio)
        peca = await _criar_peca(db, caso, "protocolada")
        await db.commit()
        try:
            with pytest.raises(HTTPException) as exc:
                await excluir(
                    caso, motivo="exclusao de teste bloqueada", payload=None,
                    db=db, cu=await _carregar_user(db, socio),
                )
            assert exc.value.status_code == 422
            await db.rollback()
            assert not await _peca_excluida(db, peca)
        finally:
            await _limpar(db, case_id=caso, client_id=cli, user_id=socio)
