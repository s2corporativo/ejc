"""T-P1-1 — o par COMPORTAMENTAL do isolamento de assinaturas.

`test_signatures_ownership.py` tem 3 de 3 testes em `inspect.getsource`: eles
afirmam que certas STRINGS aparecem no código. É o achado T-P1-1 de
`docs/auditoria-ejc/14-testes.md` — "teste que não exercita" —, e num módulo em
que o teste importa mais que na média: o `AuthMiddleware` libera TODO
`/api/signatures` ao `cliente_externo`, e o que impede um cliente de ver e
assinar o documento de OUTRO é apenas o filtro por `client_id` dentro do router.

**A diferença foi MEDIDA, não suposta.** Duas sabotagens no `signatures.py`:

| Sabotagem | `inspect.getsource` | este arquivo |
|---|---|---|
| apagar as linhas do filtro | 2 de 3 falham | 2 falham |
| **manter as linhas e matar o ramo** (`if False and …`, e `client_id == client_id` no lugar de `== cu.client_id`) | **3 de 3 PASSAM** | 2 falham |

A segunda linha é o achado: com o filtro presente no código e inerte na
execução, o teste de fonte fica **inteiramente verde** enquanto um cliente do
portal lista e assina o documento de outro. É a forma mais provável do defeito —
ninguém apaga um filtro de isolamento de propósito; ele morre por um `if` que
deixou de ser alcançado.

O arquivo antigo NÃO é substituído: ele trava a forma, e pega a sabotagem por
remoção. Este trava o comportamento. O achado T-P1-1 era a ausência do segundo.

Contra Postgres real (RUN_DB_TESTS=1).
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


class _RequestFake:
    """`assinar` grava IP e user-agent como evidência probatória (MP 2.200-2)."""
    client = SimpleNamespace(host="198.51.100.23")
    headers = {"user-agent": "Mozilla/5.0 (teste)"}


async def _criar_cliente(db, nome: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, status) "
             "VALUES (:id, 'PF', :nome, 'ativo')"),
        {"id": cid, "nome": nome},
    )
    return cid


async def _criar_user_portal(db, client_id: str):
    from app.models.user import User

    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, "
            " is_active, client_id) "
            "VALUES (:id, :email, 'x', 'Cliente Portal', 'cliente_externo', true, :cid)"
        ),
        {"id": uid, "email": f"portal-{uid[:8]}@teste.local", "cid": client_id},
    )
    await db.commit()
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _criar_solicitacao(db, client_id: str) -> tuple[str, str]:
    """Devolve (signature_request_id, document_id)."""
    doc_id, sig_id = str(uuid4()), str(uuid4())
    await db.execute(
        text(
            "INSERT INTO documents (id, titulo, filename, filepath, client_id) "
            "VALUES (:id, 'Contrato de honorários', 'contrato.pdf', "
            "        '/tmp/contrato.pdf', :cid)"
        ),
        {"id": doc_id, "cid": client_id},
    )
    await db.execute(
        text(
            "INSERT INTO signature_requests "
            "(id, document_id, client_id, status, hash_sha256) "
            "VALUES (:id, :doc, :cid, 'pendente', :h)"
        ),
        {"id": sig_id, "doc": doc_id, "cid": client_id, "h": "a" * 64},
    )
    await db.commit()
    return sig_id, doc_id


async def _limpar(db, sig_ids=(), doc_ids=(), client_ids=(), user_ids=()):
    for sid in sig_ids:
        await db.execute(text("DELETE FROM audit_logs WHERE registro_id = :id"), {"id": sid})
        await db.execute(text("DELETE FROM signature_requests WHERE id = :id"), {"id": sid})
    for did in doc_ids:
        await db.execute(text("DELETE FROM documents WHERE id = :id"), {"id": did})
    for uid in user_ids:
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


async def test_cliente_do_portal_ve_apenas_as_proprias_solicitacoes():
    """O invariante que sustenta a liberação de /api/signatures no middleware."""
    from app.core.database import AsyncSessionLocal
    from app.routers.signatures import listar

    async with AsyncSessionLocal() as db:
        cli_a = await _criar_cliente(db, "Cliente A")
        cli_b = await _criar_cliente(db, "Cliente B")
        await db.commit()
        user_a = await _criar_user_portal(db, cli_a)
        sig_a, doc_a = await _criar_solicitacao(db, cli_a)
        sig_b, doc_b = await _criar_solicitacao(db, cli_b)
        try:
            vistas = (await listar(db, user_a))["data"]
            ids = {s["id"] for s in vistas}
            assert sig_a in ids, "o cliente não vê a PRÓPRIA solicitação"
            assert sig_b not in ids, (
                "vazamento: cliente do portal enxergou a solicitação de OUTRO cliente"
            )
            # E a resposta não carrega o client_id alheio por nenhuma via —
            # nem em `signatarios`, que resolve usuários por client_id.
            assert cli_b not in str(vistas)
        finally:
            await _limpar(db, [sig_a, sig_b], [doc_a, doc_b], [cli_a, cli_b], [user_a.id])


async def test_cliente_nao_assina_documento_de_outro_e_recebe_404():
    """404, não 403: o 403 confirmaria que a solicitação do outro existe."""
    from app.core.database import AsyncSessionLocal
    from app.routers.signatures import assinar

    async with AsyncSessionLocal() as db:
        cli_a = await _criar_cliente(db, "Cliente A")
        cli_b = await _criar_cliente(db, "Cliente B")
        await db.commit()
        user_a = await _criar_user_portal(db, cli_a)
        sig_b, doc_b = await _criar_solicitacao(db, cli_b)
        try:
            with pytest.raises(HTTPException) as exc:
                await assinar(sig_b, _RequestFake(), db, user_a)
            assert exc.value.status_code == 404

            # E o documento do outro segue PENDENTE — nada foi gravado nele.
            status = (await db.execute(
                text("SELECT status, assinado_por_user FROM signature_requests "
                     "WHERE id = :id"),
                {"id": sig_b},
            )).mappings().first()
            assert status["status"] == "pendente"
            assert status["assinado_por_user"] is None
        finally:
            await _limpar(db, [sig_b], [doc_b], [cli_a, cli_b], [user_a.id])


async def test_cliente_assina_a_propria_e_a_evidencia_probatoria_e_gravada():
    """O caminho feliz — sem ele, os testes de negação provariam só que TUDO é
    recusado. E a assinatura vale pela EVIDÊNCIA (MP 2.200-2): quem, quando,
    de qual IP, sobre qual hash."""
    from app.core.database import AsyncSessionLocal
    from app.routers.signatures import assinar

    async with AsyncSessionLocal() as db:
        cli_a = await _criar_cliente(db, "Cliente A")
        await db.commit()
        user_a = await _criar_user_portal(db, cli_a)
        sig_a, doc_a = await _criar_solicitacao(db, cli_a)
        try:
            resp = await assinar(sig_a, _RequestFake(), db, user_a)
            assert resp["comprovante"]["hash_documento"] == "a" * 64

            linha = (await db.execute(
                text("SELECT status, assinado_em, assinado_por_user, ip, user_agent "
                     "FROM signature_requests WHERE id = :id"),
                {"id": sig_a},
            )).mappings().first()
            assert linha["status"] == "assinado"
            assert linha["assinado_por_user"] == user_a.id
            assert linha["assinado_em"] is not None
            # IP REAL do signatário, não o loopback do proxy — é prova.
            assert linha["ip"] == "198.51.100.23"
            assert "Mozilla" in linha["user_agent"]

            # E a trilha de auditoria registra o ato.
            acoes = [r[0] for r in (await db.execute(
                text("SELECT acao FROM audit_logs WHERE registro_id = :id"),
                {"id": sig_a},
            )).all()]
            assert "ASSINATURA" in acoes
        finally:
            await _limpar(db, [sig_a], [doc_a], [cli_a], [user_a.id])


async def test_assinar_duas_vezes_responde_409():
    """Reassinar não pode sobrescrever a evidência da primeira assinatura."""
    from app.core.database import AsyncSessionLocal
    from app.routers.signatures import assinar

    async with AsyncSessionLocal() as db:
        cli_a = await _criar_cliente(db, "Cliente A")
        await db.commit()
        user_a = await _criar_user_portal(db, cli_a)
        sig_a, doc_a = await _criar_solicitacao(db, cli_a)
        try:
            await assinar(sig_a, _RequestFake(), db, user_a)
            primeira = (await db.execute(
                text("SELECT assinado_em FROM signature_requests WHERE id = :id"),
                {"id": sig_a},
            )).scalar()

            with pytest.raises(HTTPException) as exc:
                await assinar(sig_a, _RequestFake(), db, user_a)
            assert exc.value.status_code == 409

            depois = (await db.execute(
                text("SELECT assinado_em FROM signature_requests WHERE id = :id"),
                {"id": sig_a},
            )).scalar()
            assert depois == primeira, "a data da 1ª assinatura foi reescrita"
        finally:
            await _limpar(db, [sig_a], [doc_a], [cli_a], [user_a.id])


@pytest.mark.parametrize("role", ["advogado", "socio", "admin", "secretaria"])
async def test_apenas_o_cliente_assina_pelo_portal(role):
    """Assinar é ato do CLIENTE. Nenhum perfil interno assina por ele — nem o
    sócio: a assinatura vale por identificar quem consentiu."""
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.signatures import assinar

    async with AsyncSessionLocal() as db:
        cli_a = await _criar_cliente(db, "Cliente A")
        await db.commit()
        sig_a, doc_a = await _criar_solicitacao(db, cli_a)
        uid = str(uuid4())
        await db.execute(
            text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
                 "VALUES (:id, :email, 'x', 'Interno', :role, true)"),
            {"id": uid, "email": f"int-{uid[:8]}@teste.local", "role": role},
        )
        await db.commit()
        staff = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        try:
            with pytest.raises(HTTPException) as exc:
                await assinar(sig_a, _RequestFake(), db, staff)
            assert exc.value.status_code == 403
            assert "cliente" in exc.value.detail.lower()
        finally:
            await _limpar(db, [sig_a], [doc_a], [cli_a], [uid])
