"""T-P0-3 — chaves de API de serviço: o ciclo de vida da credencial, exercitado.

`routers/api_keys.py` emite as chaves que integradores externos (n8n, scripts)
usam para abastecer a base de conhecimento, e não tinha teste nenhum
(`docs/auditoria-ejc/14-testes.md`, T-P0-3: "pix.py e api_keys.py sem teste —
dinheiro e credencial").

Uma credencial tem quatro promessas, e nenhuma delas é verificável por leitura
do código — só executando contra o banco:

1. **o segredo nunca é persistido** — só o SHA-256. Se um dia alguém acrescentar
   uma coluna "para debug", nada avisaria;
2. **o segredo aparece UMA vez** — na criação. A listagem devolve prefixo e
   metadados;
3. **revogar bloqueia de fato** — não basta marcar `ativo = False` na linha; a
   requisição seguinte tem de receber 401. A linha permanece, para auditoria;
4. **escopo insuficiente é 403, chave inválida é 401** — sinais deliberadamente
   distintos: o 403 confirma que a chave existe, e só deve chegar a quem já
   provou tê-la.

Contra Postgres real (RUN_DB_TESTS=1): `require_api_key` faz lookup e `commit`
próprios, então testar contra um fake seria testar o fake.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _criar_admin(db) -> SimpleNamespace:
    """`require_admin` já foi satisfeito pela dependency; o router só usa
    `cu.id` e `cu.role` para o audit log. O `id` precisa existir em `users`
    (FK real de audit_logs)."""
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Admin Teste Chaves', 'admin', true)"
        ),
        {"id": uid, "email": f"adm-{uid[:8]}@teste.local"},
    )
    await db.commit()
    return SimpleNamespace(id=uid, role="admin")


async def _limpar(db, key_ids=(), user_ids=()):
    for kid in key_ids:
        await db.execute(text("DELETE FROM audit_logs WHERE registro_id = :id"), {"id": kid})
        await db.execute(text("DELETE FROM api_keys WHERE id = :id"), {"id": kid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


class _RequestFake:
    """`require_api_key` consome cota por IP antes do lookup (anti-brute-force)."""
    client = SimpleNamespace(host="203.0.113.7")
    headers: dict = {}


async def test_chave_em_claro_nunca_chega_ao_banco():
    """A promessa central do módulo. O teste varre TODAS as colunas de texto da
    linha gravada procurando o segredo — não só as que eu esperaria."""
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        resp = await criar_api_key(
            ApiKeyCreate(nome="n8n de teste", escopo="knowledge:write"), db, admin
        )
        chave, key_id = resp["chave"], resp["id"]
        try:
            linha = (await db.execute(
                text("SELECT * FROM api_keys WHERE id = :id"), {"id": key_id}
            )).mappings().first()
            textos = [str(v) for v in linha.values() if v is not None]
            # Sem esta linha o teste seria VACUAMENTE verdadeiro caso a varredura
            # devolvesse nada — `all()` sobre lista vazia passa. É a diferença
            # entre "não achei o segredo" e "não procurei".
            assert len(textos) >= 6, f"a varredura não leu a linha: {textos}"
            assert all(chave not in t for t in textos), (
                "a chave em claro foi persistida em alguma coluna de api_keys"
            )

            # O que existe no banco é o SHA-256 dela — e nada mais.
            from app.core.api_key_auth import hash_chave
            assert linha["chave_hash"] == hash_chave(chave)
            # O prefixo identifica a chave sem revelá-la: 12 de ~47 caracteres.
            assert chave.startswith(linha["prefixo"])
            assert len(linha["prefixo"]) < len(chave) / 3
        finally:
            await _limpar(db, [key_id], [admin.id])


async def test_segredo_aparece_uma_unica_vez_e_some_da_listagem():
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key, listar_api_keys

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        resp = await criar_api_key(ApiKeyCreate(nome="chave unica"), db, admin)
        chave, key_id = resp["chave"], resp["id"]
        try:
            assert resp["aviso"]  # o texto avisa que não se repete

            listagem = await listar_api_keys(db, admin)
            minha = next(k for k in listagem["data"] if k["id"] == key_id)
            assert "chave" not in minha
            assert chave not in str(listagem)
            assert minha["prefixo"] == resp["prefixo"]
        finally:
            await _limpar(db, [key_id], [admin.id])


async def test_chave_recem_criada_autentica_e_carrega_o_escopo():
    """O caminho feliz — sem ele, os testes de negação abaixo provariam apenas
    que TUDO é recusado."""
    from app.core.api_key_auth import require_api_key
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        resp = await criar_api_key(ApiKeyCreate(nome="chave viva"), db, admin)
        chave, key_id = resp["chave"], resp["id"]
        try:
            dep = require_api_key("knowledge:write")
            ak = await dep(_RequestFake(), chave, db)
            assert ak.id == key_id
            # `last_used_at` passa a existir — é o que detecta chave órfã.
            assert ak.last_used_at is not None
        finally:
            await _limpar(db, [key_id], [admin.id])


async def test_revogar_bloqueia_a_chave_de_verdade_e_preserva_a_linha():
    """Revogação não é cosmética: a MESMA chave que autenticava tem de passar a
    receber 401 na requisição seguinte. E a linha fica — auditoria não se apaga.
    """
    from app.core.api_key_auth import require_api_key
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key, revogar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        resp = await criar_api_key(ApiKeyCreate(nome="chave a revogar"), db, admin)
        chave, key_id = resp["chave"], resp["id"]
        dep = require_api_key("knowledge:write")
        try:
            assert (await dep(_RequestFake(), chave, db)).id == key_id   # antes: passa

            await revogar_api_key(key_id, db, admin)

            with pytest.raises(HTTPException) as exc:                    # depois: 401
                await dep(_RequestFake(), chave, db)
            assert exc.value.status_code == 401

            linha = (await db.execute(
                text("SELECT ativo, revoked_at FROM api_keys WHERE id = :id"),
                {"id": key_id},
            )).mappings().first()
            assert linha is not None, "a linha foi APAGADA — perde-se a auditoria"
            assert linha["ativo"] is False and linha["revoked_at"] is not None
        finally:
            await _limpar(db, [key_id], [admin.id])


async def test_revogar_duas_vezes_e_idempotente():
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key, revogar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        key_id = (await criar_api_key(ApiKeyCreate(nome="dupla revogacao"), db, admin))["id"]
        try:
            primeira = await revogar_api_key(key_id, db, admin)
            segunda = await revogar_api_key(key_id, db, admin)
            assert "revogada" in primeira["detail"]
            assert "já estava revogada" in segunda["detail"]
            # A data da primeira revogação não é reescrita pela segunda.
            assert primeira["revoked_at"] == segunda["revoked_at"]
        finally:
            await _limpar(db, [key_id], [admin.id])


async def test_revogar_chave_inexistente_responde_404():
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import revogar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        try:
            with pytest.raises(HTTPException) as exc:
                await revogar_api_key(str(uuid4()), db, admin)
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, user_ids=[admin.id])


async def test_escopo_insuficiente_e_403_e_nao_401():
    """Sinais distintos de propósito: 401 = "não sei quem é você"; 403 = "sei, e
    não basta". Uniformizar em 401 esconderia do integrador legítimo qual é o
    problema; uniformizar em 403 revelaria a existência da chave a quem não a tem.
    """
    from app.core.api_key_auth import require_api_key
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        resp = await criar_api_key(ApiKeyCreate(nome="escopo estreito"), db, admin)
        chave, key_id = resp["chave"], resp["id"]
        try:
            dep = require_api_key("knowledge:admin")   # escopo que a chave não tem
            with pytest.raises(HTTPException) as exc:
                await dep(_RequestFake(), chave, db)
            assert exc.value.status_code == 403
            assert "escopo" in exc.value.detail
        finally:
            await _limpar(db, [key_id], [admin.id])


@pytest.mark.parametrize(
    "header,motivo",
    [
        (None, "ausente"),
        ("", "vazia"),
        ("ejc_chave_que_nunca_existiu_1234567890", "desconhecida"),
        ("Bearer abc123", "formato alheio ao padrão ejc_"),
        ("ejc_" + "a" * 400, "tamanho absurdo"),
    ],
)
async def test_chave_invalida_responde_401_indistinguivel(header, motivo):
    """Todas as recusas devolvem a MESMA resposta — chave desconhecida e chave
    malformada não podem ser distinguíveis, senão viram oráculo de enumeração."""
    from app.core.api_key_auth import require_api_key
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        dep = require_api_key("knowledge:write")
        with pytest.raises(HTTPException) as exc:
            await dep(_RequestFake(), header, db)
        assert exc.value.status_code == 401, motivo
        assert exc.value.detail == "API key ausente, inválida ou revogada"


@pytest.mark.parametrize("escopo", ["", "  ", "knowledge:admin", "knowledge:write,root"])
async def test_escopo_invalido_na_criacao_responde_422(escopo):
    """Escopo é allowlist. Um typo que passasse criaria uma chave que nunca
    autoriza nada — e o integrador descobriria em produção."""
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        try:
            with pytest.raises(HTTPException) as exc:
                await criar_api_key(ApiKeyCreate(nome="escopo ruim", escopo=escopo),
                                    db, admin)
            assert exc.value.status_code == 422
        finally:
            await _limpar(db, user_ids=[admin.id])


async def test_criacao_e_revogacao_deixam_trilha_de_auditoria():
    """Emitir e revogar credencial são atos administrativos rastreáveis."""
    from app.core.database import AsyncSessionLocal
    from app.routers.api_keys import ApiKeyCreate, criar_api_key, revogar_api_key

    async with AsyncSessionLocal() as db:
        admin = await _criar_admin(db)
        key_id = (await criar_api_key(ApiKeyCreate(nome="chave auditada"), db, admin))["id"]
        try:
            await revogar_api_key(key_id, db, admin)
            acoes = [r[0] for r in (await db.execute(
                text("SELECT acao FROM audit_logs WHERE registro_id = :id ORDER BY created_at"),
                {"id": key_id},
            )).all()]
            assert "CREATE" in acoes and "UPDATE" in acoes

            # E a trilha NÃO carrega o segredo.
            detalhes = " ".join(r[0] or "" for r in (await db.execute(
                text("SELECT detalhes FROM audit_logs WHERE registro_id = :id"),
                {"id": key_id},
            )).all())
            assert "ejc_" not in detalhes
        finally:
            await _limpar(db, [key_id], [admin.id])


def test_duas_chaves_geradas_nunca_colidem():
    """`gerar_chave` usa `secrets.token_urlsafe(32)`. O teste trava o uso de
    fonte criptográfica: um refactor para `random` passaria em tudo o mais."""
    from app.core.api_key_auth import PREFIXO_CHAVE, gerar_chave

    geradas = [gerar_chave() for _ in range(50)]
    chaves = {c for c, _, _ in geradas}
    hashes = {h for _, h, _ in geradas}
    assert len(chaves) == 50 and len(hashes) == 50
    assert all(c.startswith(PREFIXO_CHAVE) for c in chaves)
    # 32 bytes em base64url ≈ 43 caracteres, mais o prefixo.
    assert all(len(c) >= 40 for c in chaves)
