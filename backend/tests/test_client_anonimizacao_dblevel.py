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
    # socios_sociedade cascateia por FK; sociedades_cliente não tem cascata a
    # partir de clients, então sai explicitamente antes do cliente.
    await db.execute(
        text("DELETE FROM sociedades_cliente WHERE client_id = :cid"), {"cid": client_id}
    )
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

            # forcar=True passa por cima do bloqueio, mas registra isso.
            resultado = await anonimizar_cliente(
                db, client_id, executor, "socio", forcar=True,
            )
            assert resultado["bloqueios_ignorados"]
        finally:
            await _limpar_executor(db, executor)
            await _limpar(db, client_id, case_id)


async def test_anonimizacao_alcanca_as_tabelas_satelite():
    """P1-6 — o art. 17 não se cumpre apagando só `clients`.

    A auditoria integral (`docs/auditoria-ejc/12-seguranca-lgpd.md`) mostrou que
    a anonimização parava no registro do cliente, e o titular seguia
    identificável em três lugares:

    * `case_partes` — o titular costuma ser parte do próprio caso. Desde a
      migration 127 (P1-5) o documento ali é cifrado, e a anonimização tem de
      zerar as TRÊS colunas: o hash HMAC é reidentificador tanto quanto o
      ciphertext (quem já tem o CPF confirma a identidade comparando o hash);
    * `sociedades_cliente` — razão social e CNPJ da empresa do titular. Os
      SÓCIOS entram só quando SÃO o titular (casados pelo índice cego): apagar
      o quadro societário inteiro processaria dado de terceiro sem pedido dele
      e destruiria o cap table que o escritório tem dever de guardar;
    * `users` do portal — `full_name` e `email` SÃO o nome e o e-mail do
      titular. Antes o serviço só marcava `is_active = False`, o que esconde o
      login e não anonimiza nada; pior, o filtro `is_active IS TRUE` nem
      alcançava quem já estava desativado. Por isso o teste cria um portal já
      INATIVO — é o caso que a versão anterior deixava passar inteiro.
    """
    from app.core.database import AsyncSessionLocal
    from app.services.client_anonimizacao import anonimizar_cliente
    from app.services.pii_crypto import encrypt, hash_documento

    client_id, case_id = str(uuid4()), str(uuid4())
    parte_id, parte_sem_vinculo_id = str(uuid4()), str(uuid4())
    soc_id, socio_id, socio_terceiro_id, user_id = (str(uuid4()) for _ in range(4))
    # `_criar_cliente` grava este CPF no titular — as satélites reconhecem o
    # titular pelo MESMO índice cego.
    cpf_titular, doc_terceiro = "39053344705", "11144477735"

    async with AsyncSessionLocal() as db:
        await _criar_cliente(db, client_id)
        # `encerrado` não está em _STATUS_BLOQUEIA_ANONIMIZACAO — o caso existe
        # (para pendurar a parte) sem disparar o bloqueio de representação ativa.
        await _criar_caso(db, case_id, client_id, status="encerrado")
        await db.execute(
            text(
                "INSERT INTO case_partes "
                "(id, case_id, tipo, nome, cpf_cnpj_enc, cpf_cnpj_hash, "
                " cpf_cnpj_mascarado, email, telefone, "
                " representante_legal, client_id) "
                "VALUES (:id, :cid, 'autor', 'Fulano de Tal', :enc, :hash, "
                "        '***.533.447-**', :email, "
                "        '31999998888', 'Representante Fulano', :clid)"
            ),
            {"id": parte_id, "cid": case_id, "enc": encrypt(cpf_titular),
             "hash": hash_documento(cpf_titular),
             "email": "fulano@teste.local", "clid": client_id},
        )
        # Parte do MESMO titular, criada SEM `client_id` — é o que `TabPartes.tsx`
        # e o fluxo de importação de documento produzem (nenhum dos dois envia o
        # campo). O vínculo explícito não existe; só o índice cego a alcança.
        await db.execute(
            text(
                "INSERT INTO case_partes "
                "(id, case_id, tipo, nome, cpf_cnpj_enc, cpf_cnpj_hash, "
                " cpf_cnpj_mascarado) "
                "VALUES (:id, :cid, 'autor', 'Fulano de Tal', :enc, :hash, "
                "        '***.533.447-**')"
            ),
            {"id": parte_sem_vinculo_id, "cid": case_id,
             "enc": encrypt(cpf_titular), "hash": hash_documento(cpf_titular)},
        )
        await db.execute(
            text(
                "INSERT INTO sociedades_cliente "
                "(id, client_id, razao_social, cnpj, tipo_societario) "
                "VALUES (:id, :clid, 'Fulano Participações LTDA', "
                "        '12.345.678/0001-99', 'LTDA')"
            ),
            {"id": soc_id, "clid": client_id},
        )
        # Sócio que É o titular (mesmo documento) → deve ser anonimizado.
        await db.execute(
            text(
                "INSERT INTO socios_sociedade "
                "(id, sociedade_id, nome, quotas, documento_enc, documento_hash, "
                " documento_mascarado) "
                "VALUES (:id, :sid, 'Fulano de Tal', 60, :enc, :hash, '***.533.447-**')"
            ),
            {"id": socio_id, "sid": soc_id,
             "enc": encrypt(cpf_titular), "hash": hash_documento(cpf_titular)},
        )
        # Sócio TERCEIRO, na mesma sociedade → NÃO pode ser tocado. É outro
        # titular de dados, não pediu esquecimento nenhum, e o cap table é
        # histórico que o escritório tem dever de guardar.
        await db.execute(
            text(
                "INSERT INTO socios_sociedade "
                "(id, sociedade_id, nome, quotas, documento_enc, documento_hash, "
                " documento_mascarado) "
                "VALUES (:id, :sid, 'Beltrana Terceira', 40, :enc, :hash, "
                "        '***.444.777-**')"
            ),
            {"id": socio_terceiro_id, "sid": soc_id,
             "enc": encrypt(doc_terceiro), "hash": hash_documento(doc_terceiro)},
        )
        await db.execute(
            text(
                "INSERT INTO users "
                "(id, email, hashed_password, full_name, role, is_active, phone, client_id) "
                "VALUES (:id, :email, 'x', 'Fulano de Tal', 'cliente_externo', "
                "        false, '31999998888', :clid)"
            ),
            {"id": user_id, "email": f"portal-{user_id[:8]}@teste.local",
             "clid": client_id},
        )
        executor = await _criar_executor(db)
        await db.commit()

        try:
            await anonimizar_cliente(
                db, client_id, executor, "socio", motivo="teste satélites",
            )

            parte = (await db.execute(
                text("SELECT nome, cpf_cnpj_enc, cpf_cnpj_hash, cpf_cnpj_mascarado, "
                     "email, telefone, representante_legal "
                     "FROM case_partes WHERE id = :id"),
                {"id": parte_id},
            )).mappings().first()
            assert parte["cpf_cnpj_enc"] is None, "CPF cifrado sobreviveu em case_partes"
            assert parte["cpf_cnpj_hash"] is None, "hash HMAC é reidentificador — tem de sair"
            assert parte["cpf_cnpj_mascarado"] is None
            assert parte["nome"] == "[ANONIMIZADO — LGPD ART. 17]"
            assert parte["email"] is None
            assert parte["telefone"] is None
            assert parte["representante_legal"] is None

            # A parte SEM `client_id` — a que a interface cria — também sai.
            sem_vinculo = (await db.execute(
                text("SELECT nome, cpf_cnpj_enc, cpf_cnpj_hash, cpf_cnpj_mascarado "
                     "FROM case_partes WHERE id = :id"),
                {"id": parte_sem_vinculo_id},
            )).mappings().first()
            assert sem_vinculo["cpf_cnpj_enc"] is None, (
                "parte criada pela interface (sem client_id) escapou da "
                "anonimização — o CPF do titular segue recuperável"
            )
            assert sem_vinculo["cpf_cnpj_hash"] is None
            assert sem_vinculo["cpf_cnpj_mascarado"] is None
            assert sem_vinculo["nome"] == "[ANONIMIZADO — LGPD ART. 17]"

            soc = (await db.execute(
                text("SELECT razao_social, cnpj FROM sociedades_cliente WHERE id = :id"),
                {"id": soc_id},
            )).mappings().first()
            assert soc["cnpj"] is None
            assert soc["razao_social"] == "[ANONIMIZADO — LGPD ART. 17]"

            socio = (await db.execute(
                text("SELECT nome, documento_enc, documento_hash, documento_mascarado "
                     "FROM socios_sociedade WHERE id = :id"),
                {"id": socio_id},
            )).mappings().first()
            assert socio["documento_enc"] is None
            assert socio["documento_hash"] is None, "hash HMAC é reidentificador — tem de sair"
            assert socio["documento_mascarado"] is None
            assert socio["nome"] == "[ANONIMIZADO — LGPD ART. 17]"

            # E o TERCEIRO segue intacto. Este é o par indispensável do teste
            # acima: sem ele, "anonimizou o sócio certo" e "apagou o quadro
            # societário inteiro" passam pela mesma asserção.
            terceiro = (await db.execute(
                text("SELECT nome, documento_enc, documento_hash, documento_mascarado "
                     "FROM socios_sociedade WHERE id = :id"),
                {"id": socio_terceiro_id},
            )).mappings().first()
            assert terceiro["nome"] == "Beltrana Terceira", (
                "sócio de terceiro foi anonimizado — o art. 17 é direito do "
                "TITULAR, não autorização para apagar quem está ao redor"
            )
            assert terceiro["documento_enc"] is not None
            assert terceiro["documento_hash"] == hash_documento(doc_terceiro)
            assert terceiro["documento_mascarado"] == "***.444.777-**"

            usuario = (await db.execute(
                text("SELECT full_name, email, phone, is_active FROM users WHERE id = :id"),
                {"id": user_id},
            )).mappings().first()
            assert usuario["full_name"] == "[ANONIMIZADO — LGPD ART. 17]"
            assert usuario["email"] == f"anonimizado+{user_id}@invalido.local"
            assert usuario["phone"] is None
            assert usuario["is_active"] is False
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
