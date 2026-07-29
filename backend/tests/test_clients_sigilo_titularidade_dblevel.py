"""Segregação de titularidade (sigilo interno — LGPD/EOAB) nas rotas de cliente.

Completa o fix de sigilo que antes só cobria a LISTAGEM. Trava contra regressão o
isolamento entre advogados nas rotas IRMÃS que operam sobre UM cliente:
  • GET /clients/{id}            (detalhe)      → advogado não-dono: 404
  • POST /clients/{id}/ia-analise (perfil IA)   → advogado não-dono: 404 (antes da IA)
  • POST /clients/resolver        (CPF→id+nome) → advogado não-dono: 404 (não vaza id/nome)

E garante que o que NÃO pode ser restringido continua aberto:
  • POST /clients/checar-conflito (EOAB 34-35)  → cruza a base INTEIRA, mesmo p/ não-dono,
    porém devolvendo o CPF/CNPJ apenas MASCARADO (o nome basta para o dever ético;
    o documento em claro transformaria a checagem num extrator de PII da base toda).

Regra de titularidade (espelha _filtro_visibilidade_cliente / _pode_ver_cliente):
gestão (socio/admin/superadmin) e recepção (secretaria) veem tudo; advogado/
advogado_auxiliar só o cliente cujo responsavel_id é ele OU que tem caso não
excluído em que ele é responsável/auxiliar.

Também cobre a política de senha forte na criação de acesso ao Portal
(criar-acesso): senha fraca → 400; senha forte → cria o User cliente_externo.

Postgres é OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py: chama o handler
direto com AsyncSessionLocal). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import json
import os
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
             "VALUES (:id, :email, 'x', 'Sigilo Teste', :role, true)"),
        {"id": uid, "email": f"sig-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db, nome: str, *, responsavel_id: str | None = None,
                         cpf: str | None = None) -> str:
    # Cutover C6/LGPD: sem coluna cpf em texto puro — grava cifrado + hash. O
    # resolver/checar-conflito acham o cliente pelo cpf_hash.
    from app.services.pii_crypto import normalizar_documento, encrypt, hash_documento
    cid = str(uuid4())
    cpf_n = normalizar_documento(cpf)
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status, responsavel_id, "
             "cpf_enc, cpf_hash) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo', :resp, :cpf_enc, :cpf_hash)"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local",
         "resp": responsavel_id, "cpf_enc": encrypt(cpf_n),
         "cpf_hash": hash_documento(cpf_n)},
    )
    return cid


async def _criar_caso(db, client_id: str, titulo: str, resp_id: str | None = None) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "advogado_responsavel_id) VALUES "
             "(:id, :titulo, 'civil', 'ativo', :cid, :resp)"),
        {"id": case_id, "titulo": titulo, "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    # audit_logs referencia users (FK audit_logs_user_id_fkey) — endpoints como
    # checar_conflito/criar-acesso gravam auditoria; limpar ANTES dos users,
    # senão o DELETE viola a FK, aborta a transação e nada é limpo (órfãos que
    # contaminam outros testes, ex.: test_search_dblevel).
    for cid in case_ids:
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM cases WHERE client_id = :id"), {"id": cid})
        await db.execute(
            text("DELETE FROM audit_logs WHERE user_id IN "
                 "(SELECT id FROM users WHERE client_id = :id)"),
            {"id": cid})
        await db.execute(text("DELETE FROM users WHERE client_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


# ── GET /clients/{id} — detalhe ─────────────────────────────────────────────────

async def test_detalhe_cliente_respeita_titularidade():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import detalhe

    tok = f"Det{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        # cliente_a: vínculo por responsavel_id (dono).
        cli_a = await _criar_cliente(db, f"Cliente A {tok}", responsavel_id=dono)
        # cliente_b: sem responsável, vínculo só por caso (outro é o responsável).
        cli_b = await _criar_cliente(db, f"Cliente B {tok}", responsavel_id=None)
        caso_b = await _criar_caso(db, cli_b, f"Caso B {tok}", resp_id=outro)
        await db.commit()
        try:
            u_dono = await _carregar_user(db, dono)
            u_outro = await _carregar_user(db, outro)
            u_socio = await _carregar_user(db, socio)

            # Dono vê o próprio cliente (por responsavel_id).
            assert (await detalhe(cli_a, db, u_dono)).id == cli_a
            # Gestão (socio) vê qualquer cliente.
            assert (await detalhe(cli_a, db, u_socio)).id == cli_a
            # Advogado sem vínculo → 404 (não vaza existência).
            with pytest.raises(HTTPException) as exc:
                await detalhe(cli_a, db, u_outro)
            assert exc.value.status_code == 404

            # Vínculo por CASO: outro vê cli_b; dono (sem vínculo) não.
            assert (await detalhe(cli_b, db, u_outro)).id == cli_b
            with pytest.raises(HTTPException) as exc:
                await detalhe(cli_b, db, u_dono)
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, case_ids=[caso_b],
                          user_ids=[dono, outro, socio], client_ids=[cli_a, cli_b])


# ── POST /clients/resolver — find-or-create por CPF ─────────────────────────────

async def test_resolver_nao_vaza_cliente_de_outra_carteira():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import resolver_cliente, _ResolverClienteReq

    tok = f"Res{uuid4().hex[:6]}"
    cpf = "52998224725"
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Res {tok}", responsavel_id=dono, cpf=cpf)
        await db.commit()
        try:
            u_dono = await _carregar_user(db, dono)
            u_outro = await _carregar_user(db, outro)
            u_socio = await _carregar_user(db, socio)
            req = _ResolverClienteReq(cpf=cpf)

            # Dono resolve e recebe id+nome.
            r = await resolver_cliente(req, db, u_dono)
            assert r["id"] == cli and r["criado"] is False
            # Gestão resolve qualquer um.
            assert (await resolver_cliente(req, db, u_socio))["id"] == cli
            # Advogado sem vínculo → 404: não vaza id/nome nem cria duplicata.
            with pytest.raises(HTTPException) as exc:
                await resolver_cliente(req, db, u_outro)
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, user_ids=[dono, outro, socio], client_ids=[cli])


# ── POST /clients/{id}/ia-analise — gate ANTES da IA ────────────────────────────

async def test_ia_analise_bloqueia_nao_dono_antes_da_ia():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import ia_analise_cliente

    tok = f"Ia{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente Ia {tok}", responsavel_id=dono)
        await db.commit()
        try:
            u_outro = await _carregar_user(db, outro)
            # Advogado sem vínculo → 404, levantado ANTES de qualquer chamada de
            # IA (o gate está logo após o fetch). Se vazasse, chamaria o gateway.
            with pytest.raises(HTTPException) as exc:
                await ia_analise_cliente(cli, db, u_outro)
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, user_ids=[dono, outro], client_ids=[cli])


# ── POST /clients/checar-conflito — NÃO pode ser restringido (EOAB 34-35) ────────

async def test_conflito_ainda_cruza_base_de_outra_carteira():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import checar_conflito
    from app.schemas.client import ConflitoCheckRequest

    tok = f"Cnf{uuid4().hex[:6]}"
    # CPF válido e ÚNICO no repo (não compartilhar com test_search_dblevel, que
    # usa 39053344705 — um cliente órfão aqui contaminaria a busca de lá).
    cpf = "11144477735"
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        # Cliente pertence à carteira do dono.
        cli = await _criar_cliente(db, f"Cliente Cnf {tok}", responsavel_id=dono, cpf=cpf)
        await db.commit()
        try:
            u_outro = await _carregar_user(db, outro)
            # Advogado NÃO-dono precisa enxergar o conflito (dever ético) —
            # a segregação de titularidade NÃO se aplica aqui.
            res = await checar_conflito(ConflitoCheckRequest(cpf=cpf), db, u_outro)
            assert res["conflito"] is True
            ids = [m.get("client_id") for m in res["matches"]]
            assert cli in ids

            # ...mas o dever ético para no NOME. O CPF do cliente alheio não
            # pode sair em claro: este é o único endpoint que ignora a
            # segregação de carteira, então seria o caminho para colher PII de
            # toda a base. Vale para QUALQUER string do retorno (descricao
            # inclusive), não só para o campo do documento.
            achado = next(m for m in res["matches"] if m.get("client_id") == cli)
            assert achado["documento_mascarado"] == "***.444.777-**"
            assert cpf not in json.dumps(res)
        finally:
            await _limpar(db, user_ids=[dono, outro], client_ids=[cli])


# ── POST /clients/{id}/criar-acesso — política de senha forte ────────────────────

async def test_criar_acesso_portal_rejeita_senha_fraca():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import criar_acesso_portal, CriarAcessoReq

    tok = f"Pw{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Pw {tok}")
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            # >= 8 (passa no Field), mas fraca p/ validar_forca_senha → 400.
            # .local é TLD reservado — EmailStr (email-validator>=2.3) rejeita;
            # usar domínio de documentação (.example).
            payload = CriarAcessoReq(
                email=f"portal-{tok}@teste.example", senha_inicial="fraca123")
            with pytest.raises(HTTPException) as exc:
                await criar_acesso_portal(cli, payload, db, u_socio)
            assert exc.value.status_code == 400
        finally:
            await _limpar(db, user_ids=[socio], client_ids=[cli])


async def test_criar_acesso_portal_aceita_senha_forte():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.clients import criar_acesso_portal, CriarAcessoReq

    tok = f"Pw{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Pw {tok}")
        await db.commit()
        novo_user_id = None
        try:
            u_socio = await _carregar_user(db, socio)
            payload = CriarAcessoReq(
                email=f"portal-{tok}@teste.example", senha_inicial="F0rte!Portal2026")
            r = await criar_acesso_portal(cli, payload, db, u_socio)
            novo_user_id = r["user_id"]
            criado = (await db.execute(
                select(User).where(User.id == novo_user_id))).scalar_one()
            assert criado.role.value == "cliente_externo"
            assert criado.must_change_password is True
            assert criado.client_id == cli
        finally:
            if novo_user_id:
                await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"),
                                 {"id": novo_user_id})
                await db.execute(text("DELETE FROM users WHERE id = :id"),
                                 {"id": novo_user_id})
                await db.commit()
            await _limpar(db, user_ids=[socio], client_ids=[cli])
