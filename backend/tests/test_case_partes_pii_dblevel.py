"""DB-03 (migration 159) — CPF/CNPJ das partes cifrado, backfill e esquecimento. ROW-LEVEL.

Prova contra o Postgres real (padrão dos demais *_dblevel.py):
  (a) backfill cifra + hasheia o texto puro legado, é idempotente e não
      apaga a coluna em claro (CONTRACT é futuro);
  (b) a leitura via ORM devolve o documento decifrado e a busca exata
      funciona pelo índice cego;
  (c) a anonimização do cliente (LGPD art. 17) alcança as partes vinculadas
      (nome, cpf_cnpj em claro/cifra/hash, e-mail, telefone, qualificação) e
      o CID do satélite trabalhista dos casos do cliente — sem tocar em
      partes de terceiros.
Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role="socio") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'PII Partes Teste', :role, true)"),
        {"id": uid, "email": f"pii-partes-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db, nome) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(db, client_id, status="encerrado") -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id) "
             "VALUES (:id, 'Caso PII partes', 'trabalhista', :status, :cid)"),
        {"id": case_id, "status": status, "cid": client_id},
    )
    return case_id


async def _criar_parte_sql_cru(db, case_id, nome, doc, client_id=None) -> str:
    """Como o router de SQL cru grava hoje: texto puro, sem cifra."""
    pid = str(uuid4())
    await db.execute(
        text("INSERT INTO case_partes (id, case_id, tipo, nome, cpf_cnpj, email, telefone, "
             "qualificacao, client_id, ativo) VALUES (:id, :cid, 'autor', :nome, :doc, "
             ":email, '31999990000', 'brasileiro, casado', :client, true)"),
        {"id": pid, "cid": case_id, "nome": nome, "doc": doc,
         "email": f"{pid[:8]}@teste.local", "client": client_id},
    )
    return pid


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    await db.rollback()
    await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
    for uid in user_ids:
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
    for cid in case_ids:
        await db.execute(text("DELETE FROM trabalhista_cases WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM case_partes WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_backfill_cifra_legado_e_e_idempotente():
    from app.core.database import AsyncSessionLocal
    from app.models.case_parte import CaseParte
    from app.services.case_parte_pii import backfill_case_partes_pii
    from app.services.pii_crypto import hash_documento

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db, f"Cliente PII {tok}")
        caso = await _criar_caso(db, cli)
        p_ok = await _criar_parte_sql_cru(db, caso, f"Parte {tok}", "153.509.460-56")
        p_lixo = await _criar_parte_sql_cru(db, caso, f"Lixo {tok}", "sem-digitos")
        await db.commit()
        try:
            r1 = await backfill_case_partes_pii(db, lote=1)  # lote=1 força keyset
            assert r1["cifradas"] >= 1 and r1["ignoradas_sem_digitos"] >= 1

            linha = (await db.execute(
                text("SELECT cpf_cnpj, cpf_cnpj_enc, cpf_cnpj_hash FROM case_partes WHERE id = :id"),
                {"id": p_ok},
            )).one()
            assert linha.cpf_cnpj == "153.509.460-56", "CONTRACT é futuro: texto puro fica"
            assert linha.cpf_cnpj_enc and "15350946056" not in linha.cpf_cnpj_enc
            assert linha.cpf_cnpj_hash == hash_documento("15350946056")

            lixo = (await db.execute(
                text("SELECT cpf_cnpj_enc FROM case_partes WHERE id = :id"), {"id": p_lixo}
            )).scalar()
            assert lixo is None

            # Idempotente: nada mais a cifrar nestas linhas.
            enc_antes = linha.cpf_cnpj_enc
            await backfill_case_partes_pii(db)
            enc_depois = (await db.execute(
                text("SELECT cpf_cnpj_enc FROM case_partes WHERE id = :id"), {"id": p_ok}
            )).scalar()
            assert enc_depois == enc_antes

            # ORM: leitura decifrada + busca exata pelo índice cego.
            parte = (await db.execute(select(CaseParte).where(CaseParte.id == p_ok))).scalar_one()
            assert parte.cpf_cnpj == "15350946056"
            achada = (await db.execute(
                select(CaseParte.id).where(CaseParte.cpf_cnpj_hash == hash_documento("15350946056"))
            )).scalars().all()
            assert p_ok in achada
        finally:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


async def test_orm_grava_so_cifrado_e_downgrade_teria_o_que_restaurar():
    from app.core.database import AsyncSessionLocal
    from app.models.case_parte import CaseParte

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db, f"Cliente ORM {tok}")
        caso = await _criar_caso(db, cli)
        pid = str(uuid4())
        db.add(CaseParte(id=pid, case_id=caso, tipo="reu", nome=f"Reu {tok}",
                         cpf_cnpj="12.345.678/0001-95", ativo=True))
        await db.commit()
        try:
            linha = (await db.execute(
                text("SELECT cpf_cnpj, cpf_cnpj_enc, cpf_cnpj_hash FROM case_partes WHERE id = :id"),
                {"id": pid},
            )).one()
            assert linha.cpf_cnpj is None
            assert linha.cpf_cnpj_enc is not None and linha.cpf_cnpj_hash is not None
        finally:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


async def test_anonimizacao_alcanca_partes_do_cliente_e_cid():
    from app.core.database import AsyncSessionLocal
    from app.services.client_anonimizacao import anonimizar_cliente
    from app.services.pii_crypto import encrypt, hash_documento

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        executor = await _criar_user(db)
        cli = await _criar_cliente(db, f"Cliente Esquecer {tok}")
        outro_cli = await _criar_cliente(db, f"Outro Cliente {tok}")
        caso = await _criar_caso(db, cli, status="encerrado")
        caso_outro = await _criar_caso(db, outro_cli, status="encerrado")
        p_cli = await _criar_parte_sql_cru(db, caso, f"Autor {tok}", "153.509.460-56", client_id=cli)
        p_terceiro = await _criar_parte_sql_cru(db, caso, f"Testemunha {tok}", "111.444.777-35")
        p_outro = await _criar_parte_sql_cru(db, caso_outro, f"Autor Outro {tok}", "222.333.444-05",
                                             client_id=outro_cli)
        # Parte já cifrada (pós-backfill) do cliente: cifra e hash também somem.
        await db.execute(
            text("UPDATE case_partes SET cpf_cnpj_enc = :e, cpf_cnpj_hash = :h WHERE id = :id"),
            {"e": encrypt("15350946056"), "h": hash_documento("15350946056"), "id": p_cli},
        )
        await db.execute(
            text("INSERT INTO trabalhista_cases (id, case_id, tipo, fase, cid) "
                 "VALUES (:id, :cid, 'acidente_trabalho', 'pre_processual', 'S72.0')"),
            {"id": str(uuid4()), "cid": caso},
        )
        await db.execute(
            text("INSERT INTO trabalhista_cases (id, case_id, tipo, fase, cid) "
                 "VALUES (:id, :cid, 'acidente_trabalho', 'pre_processual', 'M54.5')"),
            {"id": str(uuid4()), "cid": caso_outro},
        )
        await db.commit()
        try:
            resultado = await anonimizar_cliente(db, cli, executor, "socio", motivo="teste")
            assert resultado["partes_anonimizadas"] == 1
            assert resultado["cids_removidos"] == 1

            anon = (await db.execute(
                text("SELECT nome, cpf_cnpj, cpf_cnpj_enc, cpf_cnpj_hash, email, telefone, "
                     "qualificacao FROM case_partes WHERE id = :id"), {"id": p_cli},
            )).one()
            assert anon.nome == "[ANONIMIZADO — LGPD ART. 17]"
            assert anon.cpf_cnpj is None and anon.cpf_cnpj_enc is None and anon.cpf_cnpj_hash is None
            assert anon.email is None and anon.telefone is None and anon.qualificacao is None

            # Terceiro no mesmo caso e parte de OUTRO cliente: intactos.
            for pid, doc in ((p_terceiro, "111.444.777-35"), (p_outro, "222.333.444-05")):
                intacta = (await db.execute(
                    text("SELECT nome, cpf_cnpj FROM case_partes WHERE id = :id"), {"id": pid}
                )).one()
                assert intacta.cpf_cnpj == doc and tok in intacta.nome

            cids = dict((await db.execute(
                text("SELECT case_id, cid FROM trabalhista_cases WHERE case_id IN (:a, :b)"),
                {"a": caso, "b": caso_outro},
            )).all())
            assert cids[caso] is None and cids[caso_outro] == "M54.5"
        finally:
            await _limpar(db, case_ids=[caso, caso_outro], user_ids=[executor],
                          client_ids=[cli, outro_cli])
