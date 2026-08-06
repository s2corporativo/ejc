"""Cutover C6/LGPD (migration 112) — CPF/CNPJ nunca em texto puro. ROW-LEVEL.

Prova, contra o Postgres real (padrão dos demais *_dblevel.py), que após o
cutover:
  (a) criar cliente NÃO grava documento em texto puro — a coluna nem existe e o
      valor guardado (cpf_enc) é ciphertext, não o número;
  (b) buscar por CPF/CNPJ COMPLETO acha o cliente via índice cego (hash);
  (c) a resposta de API (ClientResponse) devolve o CPF DECIFRADO, não o cipher;
  (d) a checagem de conflito de interesses (EOAB) acha o cliente pelo hash.

Sem RUN_DB_TESTS=1, pula (nunca conecta em produção).
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


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    from app.core.database import engine
    await engine.dispose()
    yield
    await engine.dispose()


async def _criar_user(db, role: str = "socio") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Cutover Teste', :role, true)"),
        {"id": uid, "email": f"cut-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, user_ids=None, client_ids=None):
    for cid in (client_ids or []):
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE registro_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    for uid in (user_ids or []):
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


async def test_criar_nao_grava_plaintext_e_api_decifra():
    """(a) + (c): o POST /clients cifra o CPF (sem coluna em texto puro) e a
    resposta serializada devolve o número DECIFRADO — nunca o ciphertext."""
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import criar, detalhe
    from app.schemas.client import ClientCreate, ClientResponse
    from app.services.pii_crypto import decrypt, hash_documento

    cpf_digitado = "529.982.247-25"   # com máscara, como vem do formulário
    cpf_norm = "52998224725"
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "socio")
        await db.commit()
        cu = await _carregar_user(db, uid)
        cid = None
        try:
            criado = await criar(
                ClientCreate(tipo="PF", nome=f"Fulano Cutover {uid[:6]}", cpf=cpf_digitado),
                db, cu,
            )
            cid = criado.id

            # (a) a coluna cpf em texto puro NÃO EXISTE mais no schema.
            cols = (await db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'clients' AND column_name IN ('cpf', 'cnpj')"
            ))).scalars().all()
            assert cols == [], f"colunas de texto puro ainda existem: {cols}"

            # (a) o que está gravado é ciphertext + hash, nunca o número.
            row = (await db.execute(
                text("SELECT cpf_enc, cpf_hash, cnpj_enc FROM clients WHERE id = :id"),
                {"id": cid},
            )).mappings().first()
            assert row["cpf_enc"] and cpf_norm not in row["cpf_enc"], "vazou plaintext no cpf_enc"
            assert cpf_digitado not in row["cpf_enc"]
            assert decrypt(row["cpf_enc"]) == cpf_norm      # decifra p/ o normalizado
            assert row["cpf_hash"] == hash_documento(cpf_norm)
            assert row["cnpj_enc"] is None                  # PF não tem CNPJ

            # (c) a resposta de API (ClientResponse) traz o CPF DECIFRADO.
            fresh = await detalhe(cid, db, cu)
            resp = ClientResponse.model_validate(fresh).model_dump()
            assert resp["cpf"] == cpf_norm
            assert resp["cnpj"] is None
        finally:
            await _limpar(db, user_ids=[uid], client_ids=[cid] if cid else None)


async def test_busca_por_cpf_completo_acha_via_hash():
    """(b): GET /clients?search=<CPF completo> acha pelo índice cego (hash);
    fragmento não casa (busca parcial por documento foi removida no cutover)."""
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import criar, listar
    from app.schemas.client import ClientCreate

    cpf_norm = "39053344705"
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "socio")
        await db.commit()
        cu = await _carregar_user(db, uid)
        cid = None
        try:
            criado = await criar(
                ClientCreate(tipo="PF", nome=f"Busca Cutover {uid[:6]}", cpf=cpf_norm),
                db, cu,
            )
            cid = criado.id

            # CPF completo (mesmo digitado com máscara) → acha via hash.
            # (page/page_size/status_f explícitos: chamando o handler direto, os
            # defaults seriam objetos Query do FastAPI, não valores.)
            achados = await listar(page=1, page_size=50, search="390.533.447-05",
                                   status_f=None, db=db, cu=cu)
            ids = {c.id for c in achados["data"]}
            assert cid in ids, "busca por CPF completo deveria achar o cliente (hash)"

            # Fragmento de documento NÃO casa (não há mais ILIKE por cpf).
            frag = await listar(page=1, page_size=50, search="390533",
                                status_f=None, db=db, cu=cu)
            assert cid not in {c.id for c in frag["data"]}
        finally:
            await _limpar(db, user_ids=[uid], client_ids=[cid] if cid else None)


async def test_conflito_de_interesses_acha_por_hash():
    """(d): detectar_conflito acha o cliente pelo hash do documento — a
    verificação ética (EOAB 34-35) não regride com a criptografia."""
    from app.core.database import AsyncSessionLocal
    from app.routers.clients import criar
    from app.schemas.client import ClientCreate
    from app.services.conflito_service import detectar_conflito

    cpf_norm = "11144477735"
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "socio")
        await db.commit()
        cu = await _carregar_user(db, uid)
        cid = None
        try:
            criado = await criar(
                ClientCreate(tipo="PF", nome=f"Conflito Cutover {uid[:6]}", cpf=cpf_norm),
                db, cu,
            )
            cid = criado.id

            resultado = await detectar_conflito(db, cpf="111.444.777-35")
            achados_ids = {a["id"] for a in resultado["achados"]
                           if a["tipo"] == "cliente_existente"}
            assert cid in achados_ids
            # E o "documento" do achado vem DECIFRADO (não ciphertext).
            doc = next(a["documento"] for a in resultado["achados"] if a.get("id") == cid)
            assert doc == cpf_norm
        finally:
            await _limpar(db, user_ids=[uid], client_ids=[cid] if cid else None)
