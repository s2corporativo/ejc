"""Segregação de titularidade (sigilo interno — LGPD/EOAB) nas rotas de
procuração (fix A1 do PR de segurança; aqui a trava anti-regressão).

Procuração expõe PII do outorgante (nome, CPF, qualificação na minuta) — herda
a MESMA regra de carteira dos clientes (_filtro_visibilidade_cliente /
_pode_ver_cliente): gestão vê tudo; advogado/advogado_auxiliar só clientes cujo
responsavel_id é ele OU com caso ativo em que atua.

Cobre:
  • GET  /procuracoes/                → listagem filtra a carteira do chamador;
  • POST /procuracoes/                → client_id de carteira alheia: 404
                                        (não vaza existência, não cria);
  • POST /procuracoes/{id}/minuta     → procuração de cliente alheio: 404
                                        (a minuta carrega a qualificação/PII);
  • POST /procuracoes/{id}/revogar    → procuração de cliente alheio: 404;
    dono e gestão seguem operando normalmente.

Postgres é OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: chama o handler
direto com AsyncSessionLocal). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


# ── Helpers (SQL cru, como nos demais *_dblevel.py) ─────────────────────────────

async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Proc Titularidade', :role, true)"),
        {"id": uid, "email": f"proc-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db, nome: str, *, responsavel_id: str | None = None) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status, responsavel_id) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo', :resp)"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local",
         "resp": responsavel_id},
    )
    return cid


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, user_ids=(), client_ids=()):
    # procuracoes → clients (FK) e audit_logs → users (FK): apagar nessa ordem.
    for cid in client_ids:
        await db.execute(text("DELETE FROM procuracoes WHERE client_id = :id"), {"id": cid})
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


def _payload(client_id: str):
    from app.schemas.procuracao import ProcuracaoCreate
    return ProcuracaoCreate(client_id=client_id, data_outorga=date.today())


# ── GET /procuracoes/ — listagem filtra a carteira ──────────────────────────────

async def test_listar_procuracoes_filtra_carteira():
    from app.core.database import AsyncSessionLocal
    from app.routers.procuracoes import criar, listar

    tok = f"PrL{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente {tok}", responsavel_id=dono)
        await db.commit()
        try:
            u_dono = await _carregar_user(db, dono)
            u_outro = await _carregar_user(db, outro)
            u_socio = await _carregar_user(db, socio)
            proc = await criar(_payload(cli), db=db, cu=u_dono)

            # Dono e gestão enxergam a procuração do cliente da carteira.
            out_dono = await listar(page=1, page_size=20, client_id=cli,
                                    vencendo=False, db=db, cu=u_dono)
            assert out_dono["total"] == 1
            assert out_dono["data"][0].id == proc.id
            out_socio = await listar(page=1, page_size=20, client_id=cli,
                                     vencendo=False, db=db, cu=u_socio)
            assert out_socio["total"] == 1
            # Advogado de outra carteira: lista VAZIA (nem existência vaza).
            out_outro = await listar(page=1, page_size=20, client_id=cli,
                                     vencendo=False, db=db, cu=u_outro)
            assert out_outro["total"] == 0 and out_outro["data"] == []
        finally:
            await _limpar(db, user_ids=[dono, outro, socio], client_ids=[cli])


# ── POST /procuracoes/ — emitir p/ cliente alheio → 404 ─────────────────────────

async def test_criar_procuracao_para_cliente_alheio_404():
    from app.core.database import AsyncSessionLocal
    from app.models.procuracao import Procuracao
    from app.routers.procuracoes import criar

    tok = f"PrC{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}", responsavel_id=dono)
        await db.commit()
        try:
            u_outro = await _carregar_user(db, outro)
            with pytest.raises(HTTPException) as exc:
                await criar(_payload(cli), db=db, cu=u_outro)
            assert exc.value.status_code == 404       # não vaza existência
            await db.rollback()
            # Nada foi criado para o cliente.
            n = (await db.execute(
                select(Procuracao).where(Procuracao.client_id == cli)
            )).scalars().all()
            assert n == []
        finally:
            await _limpar(db, user_ids=[dono, outro], client_ids=[cli])


# ── POST /procuracoes/{id}/minuta — PII da qualificação restrita à carteira ─────

async def test_minuta_de_cliente_alheio_404_e_dono_gera():
    from app.core.database import AsyncSessionLocal
    from app.routers.procuracoes import criar, gerar_minuta

    tok = f"PrM{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}", responsavel_id=dono)
        await db.commit()
        try:
            u_dono = await _carregar_user(db, dono)
            u_outro = await _carregar_user(db, outro)
            proc_id = (await criar(_payload(cli), db=db, cu=u_dono)).id

            # Advogado de outra carteira: 404 com o MESMO shape do inexistente.
            # (o gate só faz SELECTs — sem rollback aqui: rollback expiraria os
            # objetos ORM da sessão e o próximo acesso viraria lazy-load síncrono)
            with pytest.raises(HTTPException) as exc:
                await gerar_minuta(proc_id, case_id=None, db=db, cu=u_outro)
            assert exc.value.status_code == 404
            assert "Procuração não encontrada" in exc.value.detail
            # Dono gera a minuta com a qualificação do próprio cliente.
            out = await gerar_minuta(proc_id, case_id=None, db=db, cu=u_dono)
            assert out["procuracao_id"] == proc_id
            assert f"Cliente {tok}" in out["minuta"]
        finally:
            await _limpar(db, user_ids=[dono, outro], client_ids=[cli])


# ── POST /procuracoes/{id}/revogar — ato restrito à carteira ────────────────────

async def test_revogar_de_cliente_alheio_404_e_dono_revoga():
    from app.core.database import AsyncSessionLocal
    from app.models.procuracao import Procuracao
    from app.routers.procuracoes import criar, revogar

    tok = f"PrR{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente {tok}", responsavel_id=dono)
        await db.commit()
        try:
            u_dono = await _carregar_user(db, dono)
            u_outro = await _carregar_user(db, outro)
            proc_id = (await criar(_payload(cli), db=db, cu=u_dono)).id

            # 404 vem só de SELECTs — sem rollback (vide teste da minuta).
            with pytest.raises(HTTPException) as exc:
                await revogar(proc_id, db=db, cu=u_outro)
            assert exc.value.status_code == 404
            p = (await db.execute(
                select(Procuracao).where(Procuracao.id == proc_id)
            )).scalar_one()
            assert p.revogada is False                # o 404 não revogou nada

            await revogar(proc_id, db=db, cu=u_dono)  # dono revoga normalmente
            await db.refresh(p)
            assert p.revogada is True and p.revogada_em == date.today()
        finally:
            await _limpar(db, user_ids=[dono, outro], client_ids=[cli])
