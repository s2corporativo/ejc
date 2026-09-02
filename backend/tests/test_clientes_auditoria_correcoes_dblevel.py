"""Regressão dos achados da auditoria do módulo Clientes (agosto/2026).

Cobre, contra Postgres real (mesmo padrão dos demais *_dblevel.py):
  • Achado 1 [CRÍTICA]: dossiê e relatório financeiro não podem 500 por
    referenciar clients.cpf/cnpj — dropadas na migration 112.
  • Achado 2 [ALTA]: /checar-conflito eleva a "critico" parte em caso com
    status vigente (pós-migration 126), não mais os status extintos.
  • Achado 3 [ALTA]: /verificar-conflito mascara o documento nos achados.
  • Achado 4 [MÉDIA]: dossiê usa o mesmo gate de titularidade do resto do
    módulo — advogado da carteira vê; advogado sem vínculo, não.
  • Achado 5 [MÉDIA]: exclusão de cliente bloqueia com caso em representação
    ativa (salvo forcar=true) e desativa login do portal vinculado.
  • Achado 6 [MÉDIA]: filtro `status` inválido na listagem vira 422, não 500.
  • Achado 8 [MÉDIA]: secretaria e financeiro veem o relatório financeiro de
    qualquer cliente (a permissão de `financeiro` deixa de ser letra morta).
  • Achado 11 [BAIXA]: wildcard de case_partes.nome escapado em /checar-conflito.

Postgres é OBRIGATÓRIO. Sem RUN_DB_TESTS=1, pula.
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


async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Auditoria Teste', :role, true)"),
        {"id": uid, "email": f"aud-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db, nome: str, *, responsavel_id: str | None = None,
                         cpf: str | None = None) -> str:
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


async def _criar_caso(db, client_id: str, titulo: str, *, status: str = "em_instrucao",
                      resp_id: str | None = None) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "advogado_responsavel_id) VALUES "
             "(:id, :titulo, 'civil', :status, :cid, :resp)"),
        {"id": case_id, "titulo": titulo, "status": status, "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _criar_parte(db, case_id: str, nome: str, *, cpf_cnpj: str | None = None) -> str:
    parte_id = str(uuid4())
    await db.execute(
        text("INSERT INTO case_partes (id, case_id, tipo, nome, cpf_cnpj) "
             "VALUES (:id, :case_id, 'reu', :nome, :cpf_cnpj)"),
        {"id": parte_id, "case_id": case_id, "nome": nome, "cpf_cnpj": cpf_cnpj},
    )
    return parte_id


async def _criar_fee(db, client_id: str, *, valor: float = 100.0) -> str:
    fee_id = str(uuid4())
    await db.execute(
        text("INSERT INTO fees (id, tipo, status, descricao, valor, client_id) "
             "VALUES (:id, 'fixo', 'pendente', 'Honorário teste', :valor, :cid)"),
        {"id": fee_id, "valor": valor, "cid": client_id},
    )
    return fee_id


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return await db.get(User, uid)


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM case_partes WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM fees WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM fees WHERE client_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE client_id = :id"), {"id": cid})
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(
            text("DELETE FROM audit_logs WHERE user_id IN "
                 "(SELECT id FROM users WHERE client_id = :id)"),
            {"id": cid})
        await db.execute(text("DELETE FROM users WHERE client_id = :id"), {"id": cid})
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


async def test_dossie_cliente_nao_quebra_apos_cutover_pii():
    from app.core.database import AsyncSessionLocal
    from app.routers.dossie_cliente import dossie_cliente

    tok = f"Dos{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Dossie {tok}", cpf="52998224725")
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            resp = await dossie_cliente(cli, db, u_socio)
            assert resp["cliente"]["id"] == cli
            assert resp["cliente"]["cpf_cnpj"] == "***.982.247-**"
        finally:
            await _limpar(db, user_ids=[socio], client_ids=[cli])


async def test_relatorio_financeiro_nao_quebra_apos_cutover_pii():
    from app.core.database import AsyncSessionLocal
    from app.routers.relatorio_cliente import relatorio_financeiro_cliente

    tok = f"Rel{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Relatorio {tok}", cpf="11144477735")
        await _criar_fee(db, cli, valor=250.0)
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            resp = await relatorio_financeiro_cliente(cli, db, u_socio)
            assert resp["cliente"]["id"] == cli
            assert resp["cliente"]["cpf_cnpj"] == "***.444.777-**"
            assert resp["resumo"]["total"] == 250.0
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[socio])


async def test_checar_conflito_critico_com_status_de_caso_vigente():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import checar_conflito
    from app.schemas.client import ConflitoCheckRequest

    tok = f"Conf{uuid4().hex[:6]}"
    nome_parte = f"Fulano Conflitante {tok}"
    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db, "advogado")
        outro_cliente = await _criar_cliente(db, f"Outro Cliente {tok}")
        caso = await _criar_caso(db, outro_cliente, f"Caso {tok}", status="aberto")
        await _criar_parte(db, caso, nome_parte)
        await db.commit()
        try:
            u_advogado = await _carregar_user(db, advogado)
            res = await checar_conflito(
                ConflitoCheckRequest(nome=nome_parte), db, u_advogado)
            assert res["nivel"] == "critico"
        finally:
            await _limpar(db, case_ids=[caso], client_ids=[outro_cliente],
                          user_ids=[advogado])


async def test_checar_conflito_case_partes_escapa_wildcard():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import checar_conflito
    from app.schemas.client import ConflitoCheckRequest

    tok = f"Wc{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db, "advogado")
        outro_cliente = await _criar_cliente(db, f"Cliente Wc {tok}")
        caso = await _criar_caso(db, outro_cliente, f"Caso Wc {tok}", status="aberto")
        await _criar_parte(db, caso, f"Parte Real {tok}")
        await db.commit()
        try:
            u_advogado = await _carregar_user(db, advogado)
            res = await checar_conflito(
                ConflitoCheckRequest(nome="____"), db, u_advogado)
            assert res["nivel"] == "nenhum"
        finally:
            await _limpar(db, case_ids=[caso], client_ids=[outro_cliente],
                          user_ids=[advogado])


async def test_verificar_conflito_mascara_documento():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import verificar_conflito
    from app.schemas.client import ConflitoCheckRequest

    tok = f"Ver{uuid4().hex[:6]}"
    cpf = "39053344705"
    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente Ver {tok}", cpf=cpf)
        await db.commit()
        try:
            u_advogado = await _carregar_user(db, advogado)
            res = await verificar_conflito(
                ConflitoCheckRequest(cpf=cpf), db, u_advogado)
            achado = next(a for a in res["achados"] if a.get("id") == cli)
            assert achado["documento"] != cpf
            assert achado["documento"] == "***.533.447-**"
        finally:
            await _limpar(db, user_ids=[advogado], client_ids=[cli])


async def test_dossie_respeita_titularidade():
    from app.core.database import AsyncSessionLocal
    from app.routers.dossie_cliente import dossie_cliente

    tok = f"DosT{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        dono = await _criar_user(db, "advogado")
        outro = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente DosT {tok}", responsavel_id=dono)
        await db.commit()
        try:
            u_dono = await _carregar_user(db, dono)
            u_outro = await _carregar_user(db, outro)
            resp = await dossie_cliente(cli, db, u_dono)
            assert resp["cliente"]["id"] == cli
            with pytest.raises(HTTPException) as exc:
                await dossie_cliente(cli, db, u_outro)
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, user_ids=[dono, outro], client_ids=[cli])


async def test_remover_cliente_bloqueia_com_caso_ativo():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import remover

    tok = f"Del{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Del {tok}")
        caso = await _criar_caso(db, cli, f"Caso Del {tok}", status="em_producao")
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            with pytest.raises(HTTPException) as exc:
                await remover(cli, False, db, u_socio)
            assert exc.value.status_code == 409
            resp = await remover(cli, True, db, u_socio)
            assert resp.detail == "Cliente removido"
        finally:
            await _limpar(db, case_ids=[caso], client_ids=[cli], user_ids=[socio])


async def test_remover_cliente_desativa_portal():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.clients import remover

    tok = f"DelP{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente DelP {tok}")
        portal_uid = str(uuid4())
        await db.execute(
            text("INSERT INTO users (id, email, hashed_password, full_name, role, "
                 "is_active, client_id) VALUES "
                 "(:id, :email, 'x', 'Portal Teste', 'cliente_externo', true, :cid)"),
            {"id": portal_uid, "email": f"portal-{tok}@teste.local", "cid": cli},
        )
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            await remover(cli, False, db, u_socio)
            portal_user = await db.get(User, portal_uid)
            assert portal_user.is_active is False
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[socio])


async def test_listar_status_invalido_retorna_422():
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import listar

    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        await db.commit()
        try:
            u_socio = await _carregar_user(db, socio)
            with pytest.raises(HTTPException) as exc:
                await listar(1, 20, None, "nao-existe", db, u_socio)
            assert exc.value.status_code == 422
        finally:
            await _limpar(db, user_ids=[socio])


async def test_relatorio_financeiro_secretaria_e_financeiro_veem_qualquer_cliente():
    from app.core.database import AsyncSessionLocal
    from app.routers.relatorio_cliente import _req_fin_adv, relatorio_financeiro_cliente

    tok = f"Fin{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        outro_advogado = await _criar_user(db, "advogado")
        secretaria = await _criar_user(db, "secretaria")
        financeiro = await _criar_user(db, "financeiro")
        cli = await _criar_cliente(db, f"Cliente Fin {tok}", responsavel_id=outro_advogado)
        await db.commit()
        try:
            u_secretaria = await _carregar_user(db, secretaria)
            u_financeiro = await _carregar_user(db, financeiro)
            assert _req_fin_adv(u_secretaria) is u_secretaria
            assert _req_fin_adv(u_financeiro) is u_financeiro
            assert (await relatorio_financeiro_cliente(cli, db, u_secretaria))["cliente"]["id"] == cli
            assert (await relatorio_financeiro_cliente(cli, db, u_financeiro))["cliente"]["id"] == cli
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[outro_advogado, secretaria, financeiro])
