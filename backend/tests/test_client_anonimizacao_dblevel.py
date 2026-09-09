"""Direito ao esquecimento (LGPD art. 17) — validação ROW-LEVEL contra Postgres real.

Bloco 6b. Requer Postgres com migrations aplicadas (RUN_DB_TESTS=1, mesmo gate
do job de CI `db-validation`). Sem isso, pula — nunca conecta em produção.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_cliente(db, client_id, nome="Cliente Teste Esquecimento"):
    # Cutover C6/LGPD: documento vive cifrado (cpf_enc) + hash (cpf_hash). A
    # anonimização (art. 17) tem de zerar AMBOS — o teste verifica cpf_enc.
    from app.services.pii_crypto import encrypt, hash_documento
    cpf = "39053344705"
    await db.execute(
        text(
            "INSERT INTO clients (id, tipo, nome, cpf_enc, cpf_hash, email, status) "
            "VALUES (:id, 'PF', :nome, :cpf_enc, :cpf_hash, :email, 'ativo')"
        ),
        {"id": client_id, "nome": nome, "cpf_enc": encrypt(cpf),
         "cpf_hash": hash_documento(cpf), "email": f"{client_id[:8]}@teste.local"},
    )


async def _criar_executor(db) -> str:
    """audit_logs.user_id tem FK real para users.id — o executor da anonimização
    precisa existir (a 1ª rodada REAL destes testes no CI pegou exatamente isso:
    uuid4() avulso violava a FK). Cria um usuário socio de teste e retorna o id."""
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Executor Teste LGPD', 'socio', true)"
        ),
        {"id": uid, "email": f"exec-{uid[:8]}@teste.local"},
    )
    return uid


async def _limpar_executor(db, executor_id: str):
    # audit_logs do executor primeiro (FK), depois o usuário.
    await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
    await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": executor_id})
    await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": executor_id})


async def _criar_caso(db, case_id, client_id, status="em_instrucao"):
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id) "
            "VALUES (:id, 'Caso Teste', 'civil', :status, :cid)"
        ),
        {"id": case_id, "status": status, "cid": client_id},
    )


async def _limpar(db, client_id, case_id=None):
    if case_id:
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": case_id})
    await db.execute(text("DELETE FROM users WHERE client_id = :cid"), {"cid": client_id})
    await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    """Mesmo motivo do test_rag_isolation_dblevel.py: evita 'Event loop is
    closed' entre testes async com pytest-asyncio (loop por função)."""
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_anonimiza_cliente_sem_bloqueio():
    from app.core.database import AsyncSessionLocal
    from app.services.client_anonimizacao import anonimizar_cliente

    client_id = str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        executor = await _criar_executor(db)
        await db.commit()
        try:
            resultado = await anonimizar_cliente(
                db, client_id, executor_id=executor, executor_role="socio",
                motivo="teste automatizado",
            )
            assert resultado["client_id"] == client_id
            assert resultado["bloqueios_ignorados"] is None

            row = (await db.execute(
                text("SELECT nome, cpf_enc, cpf_hash, email, anonimizado_em FROM clients WHERE id = :id"),
                {"id": client_id},
            )).mappings().first()
            assert row["cpf_enc"] is None
            assert row["cpf_hash"] is None
            assert row["email"] is None
            assert row["nome"] == "[ANONIMIZADO — LGPD ART. 17]"
            assert row["anonimizado_em"] is not None
        finally:
            await _limpar_executor(db, executor)
            await _limpar(db, client_id)


async def test_bloqueia_com_caso_ativo_salvo_forcar():
    from app.core.database import AsyncSessionLocal
    from app.services.client_anonimizacao import anonimizar_cliente, verificar_bloqueios
    from fastapi import HTTPException

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="em_instrucao")
        executor = await _criar_executor(db)
        await db.commit()
        try:
            bloqueios = await verificar_bloqueios(db, client_id)
            assert bloqueios, "caso ativo deveria gerar bloqueio"

            with pytest.raises(HTTPException) as exc:
                await anonimizar_cliente(db, client_id, executor, "socio")
            assert exc.value.status_code == 409

            # Cliente NÃO foi tocado — dado real (cifrado) preservado até resolver o bloqueio.
            row = (await db.execute(
                text("SELECT cpf_enc, anonimizado_em FROM clients WHERE id = :id"), {"id": client_id}
            )).mappings().first()
            assert row["cpf_enc"] is not None
            assert row["anonimizado_em"] is None

            # Override irreversível sem justificativa é rejeitado.
            with pytest.raises(HTTPException) as exc_forcar:
                await anonimizar_cliente(
                    db, client_id, executor, "socio", forcar=True,
                )
            assert exc_forcar.value.status_code == 422

            # Com justificativa, o override prossegue. O WORM registra apenas
            # código controlado/metadados — nunca o texto livre fornecido.
            motivo_override = "override automatizado de representação ativa"
            resultado = await anonimizar_cliente(
                db, client_id, executor, "socio",
                motivo=motivo_override,
                forcar=True,
            )
            assert resultado["bloqueios_ignorados"]

            audit = (await db.execute(
                text(
                    "SELECT detalhes, dados_depois FROM audit_logs "
                    "WHERE user_id = :uid AND entidade = 'clients' "
                    "AND registro_id = :cid AND acao = 'ANONIMIZAR_LGPD' "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"uid": executor, "cid": client_id},
            )).mappings().first()
            assert audit is not None
            assert audit["dados_depois"]["forcado"] is True
            assert audit["dados_depois"]["codigo_justificativa"] == (
                "OVERRIDE_REPRESENTACAO_ATIVA"
            )
            assert audit["dados_depois"]["justificativa_informada"] is True
            assert "justificativa_sanitizada" not in audit["dados_depois"]
            assert motivo_override not in (audit["detalhes"] or "")
            assert motivo_override not in str(audit["dados_depois"])
        finally:
            await _limpar_executor(db, executor)
            await _limpar(db, client_id, case_id)


async def test_nao_permite_anonimizar_duas_vezes():
    from app.core.database import AsyncSessionLocal
    from app.services.client_anonimizacao import anonimizar_cliente
    from fastapi import HTTPException

    client_id = str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        executor = await _criar_executor(db)
        await db.commit()
        try:
            await anonimizar_cliente(db, client_id, executor, "socio")
            with pytest.raises(HTTPException) as exc:
                await anonimizar_cliente(db, client_id, executor, "socio")
            assert exc.value.status_code == 409
        finally:
            await _limpar_executor(db, executor)
            await _limpar(db, client_id)


async def test_db03_anonimizacao_limpa_parte_vinculada_e_cid_pf_reclamante():
    """Fase A: anonimização alcança PII cifrada relacionada sem tocar terceiros."""
    from app.core.database import AsyncSessionLocal
    from app.models.case_parte import CaseParte
    from app.models.especializado import TrabalhistaCase
    from app.services.client_anonimizacao import anonimizar_cliente

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="encerrado")
        executor = await _criar_executor(db)
        parte = CaseParte(
            id=str(uuid4()), case_id=case_id, client_id=client_id,
            tipo="autor", nome="Titular DB03",
            cpf_cnpj="390.533.447-05",
            email="titular@example.test", telefone="31988887777",
        )
        trab = TrabalhistaCase(
            id=str(uuid4()), case_id=case_id, tipo="acidente_trabalho",
            polo="reclamante", cid="S93.4",
        )
        db.add_all([parte, trab])
        await db.commit()
        try:
            resultado = await anonimizar_cliente(
                db, client_id, executor_id=executor, executor_role="socio",
                motivo="teste automatizado DB03",
            )
            assert resultado["partes_cliente_anonimizadas"] == 1
            assert resultado["cids_cliente_anonimizados"] == 1

            p = (await db.execute(text(
                "SELECT nome, cpf_cnpj, cpf_cnpj_enc, cpf_cnpj_hash, email, email_enc, "
                "telefone, telefone_enc FROM case_partes WHERE id = :id"
            ), {"id": parte.id})).mappings().one()
            assert p["nome"] == "[ANONIMIZADO — LGPD ART. 17]"
            assert all(p[k] is None for k in (
                "cpf_cnpj", "cpf_cnpj_enc", "cpf_cnpj_hash",
                "email", "email_enc", "telefone", "telefone_enc",
            ))

            c = (await db.execute(text(
                "SELECT cid, cid_enc FROM trabalhista_cases WHERE id = :id"
            ), {"id": trab.id})).mappings().one()
            assert c["cid"] is None and c["cid_enc"] is None
        finally:
            await db.execute(text("DELETE FROM trabalhista_cases WHERE case_id = :id"), {"id": case_id})
            await db.execute(text("DELETE FROM case_partes WHERE case_id = :id"), {"id": case_id})
            await _limpar_executor(db, executor)
            await _limpar(db, client_id, case_id)


async def test_db03_crud_trabalhista_cid_cifrado_sem_vazar_ciphertext():
    """CRUD do satélite mantém `cid` na API, mas só `cid_enc` no storage novo."""
    from app.core.database import AsyncSessionLocal
    from app.models.especializado import TrabalhistaTipo
    from app.models.user import User
    from app.routers.ramos_trabalhista_esp import TrabalhistaIn, trab_atualizar, trab_criar
    from app.schemas.areas_atuacao import TrabalhistaUpdate

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="encerrado")
        executor = await _criar_executor(db)
        await db.commit()
        cu = await db.get(User, executor)
        try:
            criado = await trab_criar(
                TrabalhistaIn(
                    case_id=case_id,
                    tipo=TrabalhistaTipo.acidente_trabalho,
                    polo="reclamante",
                    cid="S93.4",
                ),
                db,
                cu,
            )
            assert criado["cid"] == "S93.4"
            assert "cid_enc" not in criado

            raw = (await db.execute(text(
                "SELECT cid, cid_enc FROM trabalhista_cases WHERE id = :id"
            ), {"id": criado["id"]})).mappings().one()
            assert raw["cid"] is None and raw["cid_enc"]

            atualizado = await trab_atualizar(
                criado["id"], TrabalhistaUpdate(cid="M54.6"), db, cu,
            )
            assert atualizado["cid"] == "M54.6"
            assert "cid_enc" not in atualizado
            raw2 = (await db.execute(text(
                "SELECT cid, cid_enc FROM trabalhista_cases WHERE id = :id"
            ), {"id": criado["id"]})).mappings().one()
            assert raw2["cid"] is None and raw2["cid_enc"]
        finally:
            await db.execute(text("DELETE FROM trabalhista_cases WHERE case_id = :id"), {"id": case_id})
            await _limpar_executor(db, executor)
            await _limpar(db, client_id, case_id)
