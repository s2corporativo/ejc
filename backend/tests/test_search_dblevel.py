"""Busca global tipada (GET /search?tipo=…) — validação ROW-LEVEL.

Cobre os novos tipos de busca (parte | cpf | processo) e a regressão do
tipo=tudo com dados reais: Postgres real via `AsyncSessionLocal`, chamando o
handler `busca_global` diretamente (mesmo padrão dos demais *_dblevel.py,
ex. test_casos_dblevel.py). O handler é decorado com @limiter.limit, então
recebe um Request construído de um scope ASGI mínimo.

Postgres é OBRIGATÓRIO aqui (não dá para portar a SQLite): a busca por
cpf/processo usa func.regexp_replace(..., 'g') — PG-only. Sem RUN_DB_TESTS=1,
pula (nunca conecta em produção). A validação de contrato sem banco (422 etc.)
está em test_search.py.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


# ── Helpers de fixture (SQL cru, como nos demais *_dblevel.py) ───────────────

def _req() -> Request:
    """Request mínimo para o wrapper do slowapi (@limiter.limit)."""
    return Request({
        "type": "http", "method": "GET", "path": "/search", "headers": [],
        "query_string": b"", "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80), "scheme": "http",
    })


async def _criar_user(db, role: str = "socio") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Busca Teste', :role, true)"),
        {"id": uid, "email": f"busca-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db, nome: str, cpf: str | None = None,
                         cnpj: str | None = None) -> str:
    # Cutover C6/LGPD: sem colunas cpf/cnpj em texto puro — grava só cifrado +
    # hash (o mesmo que o cadastro real faz). Busca por documento casa via hash.
    from app.services.pii_crypto import normalizar_documento, encrypt, hash_documento
    cid = str(uuid4())
    cpf_n = normalizar_documento(cpf)
    cnpj_n = normalizar_documento(cnpj)
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, cpf_enc, cpf_hash, "
             "cnpj_enc, cnpj_hash, email, status) "
             "VALUES (:id, :tipo, :nome, :cpf_enc, :cpf_hash, "
             ":cnpj_enc, :cnpj_hash, :email, 'ativo')"),
        {"id": cid, "tipo": "PJ" if cnpj else "PF", "nome": nome,
         "cpf_enc": encrypt(cpf_n), "cpf_hash": hash_documento(cpf_n),
         "cnpj_enc": encrypt(cnpj_n), "cnpj_hash": hash_documento(cnpj_n),
         "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(db, client_id: str, titulo: str,
                      resp_id: str | None = None,
                      numero_processo: str | None = None) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "advogado_responsavel_id, numero_processo) VALUES "
             "(:id, :titulo, 'civil', 'em_instrucao', :cid, :resp, :np)"),
        {"id": case_id, "titulo": titulo, "cid": client_id,
         "resp": resp_id, "np": numero_processo},
    )
    return case_id


async def _criar_parte(db, case_id: str, nome: str,
                       cpf_cnpj: str | None = None,
                       ativo: bool = True) -> None:
    # Migration 127: `case_partes.cpf_cnpj` não existe mais em texto puro. O
    # parâmetro continua recebendo o documento como o teste o escreve (com ou
    # sem máscara) e a gravação replica o que `routers/case_partes.py` faz —
    # normaliza, cifra, hasheia e mascara. A busca por CPF que estes testes
    # exercitam passou a casar pelo HASH.
    from app.services.pii_crypto import (
        encrypt, hash_documento, mascarar_documento, normalizar_documento,
    )

    doc = normalizar_documento(cpf_cnpj)
    await db.execute(
        text("INSERT INTO case_partes "
             "(case_id, tipo, nome, cpf_cnpj_enc, cpf_cnpj_hash, "
             " cpf_cnpj_mascarado, ativo) "
             "VALUES (:cid, 'autor', :nome, :enc, :hash, :masc, :ativo)"),
        {"cid": case_id, "nome": nome, "enc": encrypt(doc),
         "hash": hash_documento(doc), "masc": mascarar_documento(doc),
         "ativo": ativo},
    )


async def _criar_processo(db, case_id: str, numero_cnj: str) -> None:
    await db.execute(
        text("INSERT INTO processes (case_id, numero_cnj) VALUES (:cid, :cnj)"),
        {"cid": case_id, "cnj": numero_cnj},
    )


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    # Ordem por FK: processos/partes → casos → auditoria → usuários → clientes.
    for cid in case_ids:
        await db.execute(text("DELETE FROM processes WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM case_partes WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


async def _buscar(db, cu, q: str, tipo: str, limit: int = 6) -> dict:
    from app.routers.search import busca_global
    return await busca_global(request=_req(), q=q, tipo=tipo,
                              limit=limit, db=db, cu=cu)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    """Isola o engine async do loop-por-função do pytest-asyncio.

    Descarta ANTES e DEPOIS: o pool asyncpg do engine global se prende ao
    primeiro loop que o usa; se um teste de OUTRO arquivo rodar antes e deixar
    o pool preso a um loop já fechado, o PRIMEIRO teste deste arquivo herdaria
    o pool contaminado e falharia com 'got Future attached to a different loop'
    (flaky, dependente de ordem — visto no CI). Descartar antes força um pool
    novo, ligado ao loop deste teste.
    """
    from app.core.database import engine
    await engine.dispose()
    yield
    await engine.dispose()


# ── tipo=parte ───────────────────────────────────────────────────────────────

async def test_parte_encontra_caso_e_deduplica():
    from app.core.database import AsyncSessionLocal

    tok = f"Zzp{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso = await _criar_caso(db, cli, f"Caso {tok}")
        # Duas partes do MESMO caso batendo na busca → o caso sai UMA vez.
        await _criar_parte(db, caso, f"{tok} Silva Primeiro")
        await _criar_parte(db, caso, f"{tok} Silva Segundo")
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            resp = await _buscar(db, cu, f"{tok} Silva", "parte")
            assert resp["tipo"] == "parte"
            assert resp["total"] == 1
            item = resp["resultados"][0]
            assert item["tipo"] == "caso"
            assert item["id"] == caso
            assert item["link"] == f"/casos/{caso}"
            assert item["subtitulo"].startswith("Parte: ")
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[uid], client_ids=[cli])


async def test_parte_respeita_escopo_de_advogado():
    from app.core.database import AsyncSessionLocal

    tok = f"Zze{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        adv1 = await _criar_user(db, "advogado")
        adv2 = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente {tok}")
        caso_meu = await _criar_caso(db, cli, f"Caso meu {tok}", resp_id=adv1)
        caso_alheio = await _criar_caso(db, cli, f"Caso alheio {tok}", resp_id=adv2)
        await _criar_parte(db, caso_meu, f"{tok} Empresa Ltda")
        await _criar_parte(db, caso_alheio, f"{tok} Empresa Ltda")
        await db.commit()
        try:
            # Advogado vê SÓ o caso em que é responsável/auxiliar.
            resp = await _buscar(db, await _carregar_user(db, adv1), tok, "parte")
            assert [i["id"] for i in resp["resultados"]] == [caso_meu]

            # Sócio (>= ROLE_LEVEL["socio"]) vê os dois.
            resp2 = await _buscar(db, await _carregar_user(db, socio), tok, "parte")
            assert {i["id"] for i in resp2["resultados"]} == {caso_meu, caso_alheio}
        finally:
            await _limpar(db, case_ids=[caso_meu, caso_alheio],
                          user_ids=[adv1, adv2, socio], client_ids=[cli])


# ── tipo=cpf ─────────────────────────────────────────────────────────────────

async def test_cpf_acha_cliente_e_parte_com_mascara_no_banco():
    """No banco os documentos estão MASCARADOS; o usuário digita SEM máscara
    (e vice-versa) — regexp_replace normaliza os dois lados."""
    from app.core.database import AsyncSessionLocal

    tok = f"Zzc{uuid4().hex[:6]}"
    cpf_cli = "529.982.247-25"     # armazenado com máscara
    cpf_parte = "153.509.460-56"   # idem
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente CPF {tok}", cpf=cpf_cli)
        caso = await _criar_caso(db, cli, f"Caso CPF {tok}")
        await _criar_parte(db, caso, f"Parte CPF {tok}", cpf_cnpj=cpf_parte)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            # Digitado sem máscara → acha o cliente cujo cpf está mascarado.
            resp = await _buscar(db, cu, "52998224725", "cpf")
            assert resp["tipo"] == "cpf"
            assert [(i["tipo"], i["id"]) for i in resp["resultados"]] == [("cliente", cli)]
            # A busca exata encontra o registro, mas a resposta minimiza PII.
            assert resp["resultados"][0]["subtitulo"] == "***.982.247-**"

            # Digitado COM máscara → normalizar_documento também resolve.
            resp2 = await _buscar(db, cu, "529.982.247-25", "cpf")
            assert [i["id"] for i in resp2["resultados"]] == [cli]

            # CPF da parte processual → devolve o caso com documento mascarado.
            resp3 = await _buscar(db, cu, "15350946056", "cpf")
            assert [(i["tipo"], i["id"]) for i in resp3["resultados"]] == [("caso", caso)]
            sub3 = resp3["resultados"][0]["subtitulo"]
            assert "***.509.460-**" in sub3
            assert cpf_parte not in sub3

            # CPF/CNPJ incompleto ou não numérico é rejeitado para impedir enumeração.
            with pytest.raises(HTTPException) as exc:
                await _buscar(db, cu, "abc", "cpf")
            assert exc.value.status_code == 422
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[uid], client_ids=[cli])


async def test_cpf_hash_exato_encontra_cliente_sem_plaintext():
    """M2: cliente JÁ MIGRADO (cpf plaintext NULL, só cpf_hash) é encontrado
    quando o usuário digita o documento COMPLETO (11 dígitos) — o índice cego
    garante a busca após a remoção das colunas legadas."""
    from app.core.database import AsyncSessionLocal
    from app.services.pii_crypto import hash_documento

    tok = f"Zzh{uuid4().hex[:6]}"
    cpf = "39053344705"
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Hash {tok}")
        # Cliente com hash SEM enc (edge: sem valor a decifrar) — prova que a
        # busca acha pelo índice cego mas o subtítulo fica vazio (nada a exibir).
        await db.execute(
            text("UPDATE clients SET cpf_hash = :h WHERE id = :id"),
            {"h": hash_documento(cpf), "id": cli})
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            resp = await _buscar(db, cu, "390.533.447-05", "cpf")
            assert [(i["tipo"], i["id"]) for i in resp["resultados"]] == [("cliente", cli)]
            # Sem plaintext, o subtítulo é vazio (nada a exibir).
            assert resp["resultados"][0]["subtitulo"] == ""

            # Fragmento é rejeitado antes da consulta para impedir enumeração.
            with pytest.raises(HTTPException) as exc:
                await _buscar(db, cu, "0533447", "cpf")
            assert exc.value.status_code == 422
        finally:
            await _limpar(db, user_ids=[uid], client_ids=[cli])


async def test_cpf_estagiario_nao_recebe_clientes():
    """M1: papel fora da matriz do CRM (estagiario) não recebe itens de
    cliente em tipo=cpf; o bloco partes→casos continua (escopado por caso)."""
    from app.core.database import AsyncSessionLocal

    tok = f"Zzg{uuid4().hex[:6]}"
    cpf = "529.982.247-25"
    async with AsyncSessionLocal() as db:
        estagiario = await _criar_user(db, "estagiario")
        cli = await _criar_cliente(db, f"Cliente Gate {tok}", cpf=cpf)
        caso = await _criar_caso(db, cli, f"Caso Gate {tok}", resp_id=estagiario)
        await _criar_parte(db, caso, f"Parte Gate {tok}", cpf_cnpj=cpf)
        await db.commit()
        try:
            resp = await _buscar(db, await _carregar_user(db, estagiario),
                                 "52998224725", "cpf")
            # Nenhum item "cliente"; o caso (via parte) aparece.
            assert [(i["tipo"], i["id"]) for i in resp["resultados"]] == [("caso", caso)]
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[estagiario],
                          client_ids=[cli])


async def test_parte_inativa_nao_aparece_em_parte_nem_cpf():
    """ALTA: parte soft-deletada (ativo=false, padrão de case_partes.py) não
    aparece em tipo=parte nem em tipo=cpf."""
    from app.core.database import AsyncSessionLocal

    tok = f"Zzi{uuid4().hex[:6]}"
    cpf = "153.509.460-56"
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Inativa {tok}")
        caso = await _criar_caso(db, cli, f"Caso Inativa {tok}")
        await _criar_parte(db, caso, f"{tok} Removida", cpf_cnpj=cpf, ativo=False)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            resp = await _buscar(db, cu, f"{tok} Removida", "parte")
            assert resp["resultados"] == []
            resp2 = await _buscar(db, cu, "15350946056", "cpf")
            assert resp2["resultados"] == []
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[uid], client_ids=[cli])


# ── tipo=processo ────────────────────────────────────────────────────────────

async def test_processo_por_numero_com_e_sem_mascara_cnj():
    from app.core.database import AsyncSessionLocal

    tok = f"Zzn{uuid4().hex[:6]}"
    numero = "1234567-89.2026.8.13.0001"
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"Cliente Proc {tok}")
        caso = await _criar_caso(db, cli, f"Caso Proc {tok}", numero_processo=numero)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            # Com máscara CNJ (ilike bruto).
            resp = await _buscar(db, cu, numero, "processo")
            assert resp["tipo"] == "processo"
            assert [i["id"] for i in resp["resultados"]] == [caso]
            assert resp["resultados"][0]["subtitulo"] == numero

            # Sem máscara (comparação só-dígitos).
            resp2 = await _buscar(db, cu, "12345678920268130001", "processo")
            assert [i["id"] for i in resp2["resultados"]] == [caso]
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[uid], client_ids=[cli])


async def test_processo_vinculado_tabela_processes_com_escopo_e_dedup():
    from app.core.database import AsyncSessionLocal

    tok = f"Zzv{uuid4().hex[:6]}"
    cnj = "7654321-98.2026.8.13.0002"
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        adv_sem_vinculo = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db, f"Cliente Vinc {tok}")
        # Caso SEM numero_processo próprio: só acha via processes.numero_cnj.
        caso = await _criar_caso(db, cli, f"Caso Vinc {tok}")
        await _criar_processo(db, caso, cnj)
        await db.commit()
        try:
            # Sócio acha o caso pelo CNJ do processo vinculado (sem máscara).
            resp = await _buscar(db, await _carregar_user(db, socio),
                                 "76543219820268130002", "processo")
            assert [(i["tipo"], i["id"]) for i in resp["resultados"]] == [("caso", caso)]
            assert resp["resultados"][0]["subtitulo"] == cnj

            # Dedup: mesmo caso via Case.numero_processo E via processes →
            # sai UMA vez só.
            await db.execute(
                text("UPDATE cases SET numero_processo = :np WHERE id = :id"),
                {"np": cnj, "id": caso})
            await db.commit()
            resp2 = await _buscar(db, await _carregar_user(db, socio), cnj, "processo")
            assert [i["id"] for i in resp2["resultados"]] == [caso]

            # Escopo (via _escopo_casos no ORM): advogado sem vínculo não vê nada.
            resp3 = await _buscar(db, await _carregar_user(db, adv_sem_vinculo),
                                  cnj, "processo")
            assert resp3["resultados"] == []
        finally:
            await _limpar(db, case_ids=[caso],
                          user_ids=[socio, adv_sem_vinculo], client_ids=[cli])


# ── tipo=tudo (regressão do comportamento clássico) ──────────────────────────

async def test_tudo_mantem_shape_antigo_e_ganha_campo_tipo():
    from app.core.database import AsyncSessionLocal

    tok = f"Zzt{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "socio")
        cli = await _criar_cliente(db, f"{tok} Cliente Regressao")
        caso = await _criar_caso(db, cli, f"{tok} Caso Regressao")
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            resp = await _buscar(db, cu, tok, "tudo")
            # Envelope: chaves antigas + o novo campo "tipo".
            assert set(resp.keys()) == {"q", "tipo", "total", "resultados"}
            assert resp["tipo"] == "tudo"
            assert resp["q"] == tok

            por_tipo = {i["tipo"]: i for i in resp["resultados"]}
            assert set(por_tipo) == {"cliente", "caso"}
            # Shape antigo de cada item, intacto.
            for item in resp["resultados"]:
                assert set(item.keys()) == {"tipo", "id", "titulo", "subtitulo", "link"}
            assert por_tipo["cliente"]["id"] == cli
            assert por_tipo["cliente"]["link"] == "/clientes"
            assert por_tipo["caso"]["id"] == caso
            assert por_tipo["caso"]["link"] == f"/casos/{caso}"
            assert resp["total"] == 2
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[uid], client_ids=[cli])


async def test_tudo_estagiario_nao_recebe_clientes():
    """P0-3 (auditoria #110): papel fora da matriz do CRM (estagiario) não
    recebe itens de cliente em tipo=tudo — mesma restrição já aplicada em
    tipo=cpf (test_cpf_estagiario_nao_recebe_clientes). O caso (próprio,
    via responsavel) continua aparecendo."""
    from app.core.database import AsyncSessionLocal

    tok = f"Zzu{uuid4().hex[:6]}"
    async with AsyncSessionLocal() as db:
        estagiario = await _criar_user(db, "estagiario")
        cli = await _criar_cliente(db, f"{tok} Cliente Tudo")
        caso = await _criar_caso(db, cli, f"{tok} Caso Tudo", resp_id=estagiario)
        await db.commit()
        try:
            resp = await _buscar(db, await _carregar_user(db, estagiario), tok, "tudo")
            # Nenhum item "cliente"; o caso próprio continua visível.
            assert "cliente" not in {i["tipo"] for i in resp["resultados"]}
            assert [(i["tipo"], i["id"]) for i in resp["resultados"]] == [("caso", caso)]
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[estagiario], client_ids=[cli])
