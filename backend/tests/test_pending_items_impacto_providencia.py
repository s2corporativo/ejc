"""Regressão da frente 12 (`docs/estrategia/EVOLUCAO_ESTRATEGICA_EJC.md`):
impacto e providência nas pendências do cliente.

Cobre duas coisas distintas:

1. **Vocabulário** (puro Pydantic, roda SEMPRE — sem banco). Inclui a
   regressão do bug pré-existente: o `<select>` de tipo em `DossieCliente.tsx`
   oferecia `procuracao`, `certidao` e `outro`, que o backend rejeitava com
   422 — quem escolhesse qualquer um dos três não conseguia salvar.
2. **Persistência** (nível de banco, exige `RUN_DB_TESTS=1`): os dois campos
   novos gravam no INSERT e voltam no GET, e o PATCH consegue tanto
   classificar quanto LIMPAR a classificação (null explícito é legítimo aqui,
   ao contrário de type/status).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.routers.pending_items import PendingItemCreate, PendingItemUpdate


# ── 1. Vocabulário — sem banco, roda em qualquer ambiente ────────────────────

@pytest.mark.parametrize(
    "tipo", ["documento", "informacao", "assinatura", "pagamento",
             "procuracao", "certidao", "outro"],
)
def test_todos_os_tipos_do_formulario_sao_aceitos(tipo):
    """Os sete valores do <select> de tipo precisam passar no backend.

    Antes desta correção o vocabulário do backend tinha só os quatro
    primeiros: escolher "Procuração", "Certidão" ou "Outro" no formulário
    devolvia 422 e a pendência não era criada.
    """
    assert PendingItemCreate(title="X", type=tipo).type == tipo


def test_tipo_fora_do_vocabulario_continua_reprovando():
    with pytest.raises(ValidationError):
        PendingItemCreate(title="X", type="tipo-inventado")


@pytest.mark.parametrize("impacto", ["alto", "medio", "baixo"])
def test_impacto_valido_e_aceito(impacto):
    assert PendingItemCreate(title="X", impacto=impacto).impacto == impacto


@pytest.mark.parametrize(
    "providencia", ["solicitar_cliente", "obter_processo", "emitir_certidao",
                    "diligencia_externa", "outro"],
)
def test_providencia_valida_e_aceita(providencia):
    item = PendingItemCreate(title="X", providencia=providencia)
    assert item.providencia == providencia


def test_impacto_e_providencia_sao_opcionais():
    """Ausência = "não avaliado", não "sem impacto" — a coluna é nullable e a
    pendência continua válida sem classificação nenhuma."""
    item = PendingItemCreate(title="X")
    assert item.impacto is None
    assert item.providencia is None


@pytest.mark.parametrize(
    "campo,valor",
    [("impacto", "altissimo"), ("impacto", ""), ("impacto", "ALTO"),
     ("providencia", "pedir_pro_cliente"), ("providencia", "")],
)
def test_valor_fora_do_vocabulario_reprova(campo, valor):
    """Inclui o caso `""`: o <select> usa string vazia para "não
    classificado", e o frontend precisa convertê-la em `undefined` antes de
    enviar — se escapar, tem que reprovar aqui em vez de gravar lixo."""
    with pytest.raises(ValidationError):
        PendingItemCreate(**{"title": "X", campo: valor})


def test_patch_aceita_null_para_limpar_classificacao():
    """Diferença deliberada em relação a type/status: aqueles são NOT NULL e
    rejeitam null explícito; impacto/providencia são nullable, e mandar null
    é a forma de desclassificar uma pendência."""
    upd = PendingItemUpdate(impacto=None, providencia=None)
    dados = upd.model_dump(exclude_unset=True)
    assert dados == {"impacto": None, "providencia": None}


def test_patch_continua_reprovando_null_em_campo_not_null():
    for campo in ("title", "type", "status"):
        with pytest.raises(ValidationError):
            PendingItemUpdate(**{campo: None})


# ── 2. Persistência — exige Postgres com as migrations aplicadas ─────────────

requer_db = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db) -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Pendencia Teste', 'socio', true)"),
        {"id": uid, "email": f"imp-{uid[:8]}@teste.local"},
    )
    return uid


async def _criar_cliente(db) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": f"Cliente Imp {cid[:8]}", "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _limpar(db, client_id: str, user_id: str) -> None:
    await db.execute(text("DELETE FROM client_pending_items WHERE client_id = :id"),
                     {"id": client_id})
    await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
    await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": user_id})
    await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    if os.getenv("RUN_DB_TESTS"):
        from app.core.database import engine
        await engine.dispose()


@requer_db
async def test_impacto_e_providencia_gravam_e_voltam_na_listagem():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.pending_items import create_pending_item, list_pending_items

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        cid = await _criar_cliente(db)
        await db.commit()
        try:
            user = await db.get(User, uid)
            criado = await create_pending_item(
                cid,
                PendingItemCreate(title="Certidão de distribuição",
                                  type="certidao", impacto="alto",
                                  providencia="emitir_certidao"),
                db, user,
            )
            assert criado["impacto"] == "alto"
            assert criado["providencia"] == "emitir_certidao"

            itens = await list_pending_items(cid, None, db, user)
            assert len(itens) == 1
            assert itens[0]["impacto"] == "alto"
            assert itens[0]["providencia"] == "emitir_certidao"
        finally:
            await _limpar(db, cid, uid)


@requer_db
async def test_pendencia_sem_classificacao_grava_null():
    """Comportamento das pendências que já existiam antes da migration 147."""
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.pending_items import create_pending_item

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        cid = await _criar_cliente(db)
        await db.commit()
        try:
            user = await db.get(User, uid)
            criado = await create_pending_item(
                cid, PendingItemCreate(title="Comprovante"), db, user)
            assert criado["impacto"] is None
            assert criado["providencia"] is None
        finally:
            await _limpar(db, cid, uid)


@requer_db
async def test_patch_classifica_e_depois_limpa():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.pending_items import (
        create_pending_item, list_pending_items, update_pending_item,
    )

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        cid = await _criar_cliente(db)
        await db.commit()
        try:
            user = await db.get(User, uid)
            item = await create_pending_item(
                cid, PendingItemCreate(title="Procuração", type="procuracao"),
                db, user)

            await update_pending_item(
                cid, item["id"],
                PendingItemUpdate(impacto="medio", providencia="solicitar_cliente"),
                db, user)
            itens = await list_pending_items(cid, None, db, user)
            assert itens[0]["impacto"] == "medio"
            assert itens[0]["providencia"] == "solicitar_cliente"

            # null explícito desclassifica (não pode virar 500 por NOT NULL).
            await update_pending_item(
                cid, item["id"],
                PendingItemUpdate(impacto=None, providencia=None), db, user)
            itens = await list_pending_items(cid, None, db, user)
            assert itens[0]["impacto"] is None
            assert itens[0]["providencia"] is None
        finally:
            await _limpar(db, cid, uid)
