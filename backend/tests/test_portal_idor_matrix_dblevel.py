"""Matriz de IDOR/segregação do Portal do Cliente — camada 3 (ROW-LEVEL, Postgres).

Complementa test_portal_idor_matrix.py (camadas 1 e 2, sem banco). Aqui provamos,
com DADOS REAIS de dois clientes distintos (A e B), que o filtro `WHERE
client_id = <meu>` de cada handler de fato isola: o cliente A, forjando ids de
recursos do cliente B, recebe 404 e SÓ enxerga o que é seu (assert positivo).

Pontos de isolamento cobertos (cada teste comenta o que prova):
  • portal.caso_detalhe / meus_casos  — caso por client_id
  • portal.documentos                 — só docs NORMAIS do próprio cliente
  • portal.financeiro                 — honorários do próprio cliente
  • portal.listar/enviar_mensagem     — chat isolado por caso do cliente
  • signatures.listar / assinar       — assinaturas por client_id (rota que o
                                        middleware LIBERA ao cliente_externo:
                                        o isolamento é 100% do router)
  • mensagens._verificar_acesso       — cross-carteira entre advogados (staff
                                        sem ownership do caso → 403)
  • portal_documentos                 — solicitações por client_id
  • portal.caso_detalhe / meus_casos  — movimento INTERNO (ia/nota) nunca chega
                                        ao cliente, só andamento processual

Padrão idêntico aos demais *_dblevel.py: handler chamado direto com
AsyncSessionLocal, SQL cru para a massa, RUN_DB_TESTS obrigatório.
"""

from __future__ import annotations

import os
import types
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


# ── Helpers de massa (SQL cru, como test_idor_subrecursos_403_dblevel.py) ──────


async def _criar_cliente(db, nome: str) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) " "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@idor.local"},
    )
    return cid


async def _criar_portal_user(db, client_id: str) -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, "
            "is_active, client_id) VALUES "
            "(:id, :email, 'x', 'Portal Teste', 'cliente_externo', true, :cid)"
        ),
        {"id": uid, "email": f"portal-{uid[:8]}@idor.local", "cid": client_id},
    )
    return uid


async def _criar_staff(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, "
            "is_active) VALUES (:id, :email, 'x', 'Staff Teste', :role, true)"
        ),
        {"id": uid, "email": f"staff-{uid[:8]}@idor.local", "role": role},
    )
    return uid


async def _criar_caso(db, client_id: str, titulo: str, resp_id: str | None = None) -> str:
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id, "
            "advogado_responsavel_id) VALUES "
            "(:id, :titulo, 'civil', 'em_instrucao', :cid, :resp)"
        ),
        {"id": case_id, "titulo": titulo, "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _criar_documento(db, client_id: str, case_id: str | None, titulo: str, confid: str = "normal") -> str:
    doc_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO documents (id, titulo, filename, filepath, client_id, "
            "case_id, confidencialidade) VALUES "
            "(:id, :titulo, :fn, :fp, :cid, :case, "
            " CAST(:conf AS docconfidencialidade))"
        ),
        {
            "id": doc_id,
            "titulo": titulo,
            "fn": f"{titulo}.pdf",
            "fp": f"2026/07/{doc_id}.pdf",
            "cid": client_id,
            "case": case_id,
            "conf": confid,
        },
    )
    return doc_id


async def _criar_fee(db, client_id: str, descricao: str) -> str:
    fee_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO fees (id, descricao, client_id, valor, data_vencimento) "
            "VALUES (:id, :desc, :cid, 1500, '2026-08-10')"
        ),
        {"id": fee_id, "desc": descricao, "cid": client_id},
    )
    return fee_id


async def _criar_signature(db, client_id: str, document_id: str, status: str = "pendente") -> str:
    sig_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO signature_requests (id, document_id, client_id, "
            "hash_sha256, status) VALUES (:id, :doc, :cid, :h, :st)"
        ),
        {"id": sig_id, "doc": document_id, "cid": client_id, "h": uuid4().hex + uuid4().hex, "st": status},
    )
    return sig_id


async def _inserir_msg_escritorio(db, case_id: str, autor_id: str, msg: str) -> None:
    await db.execute(
        text(
            "INSERT INTO portal_mensagens (case_id, autor_tipo, autor_id, "
            "autor_nome, mensagem) VALUES (:cid, 'escritorio', :aid, 'Adv', :m)"
        ),
        {"cid": case_id, "aid": autor_id, "m": msg},
    )


async def _criar_solicitacao(db, client_id: str, case_id: str) -> str:
    sol_id = str(uuid4())
    await db.execute(
        text("INSERT INTO solicitacoes_documentos (id, case_id, client_id) " "VALUES (:id, :case, :cid)"),
        {"id": sol_id, "case": case_id, "cid": client_id},
    )
    return sol_id


async def _carregar_user(db, uid: str):
    from app.models.user import User

    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, client_ids=(), user_ids=()):
    for uid in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM notifications WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM portal_mensagens WHERE autor_id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM signature_requests WHERE client_id = :id"), {"id": cid})
        await db.execute(
            text("DELETE FROM portal_mensagens WHERE case_id IN " "(SELECT id FROM cases WHERE client_id = :id)"),
            {"id": cid},
        )
        await db.execute(
            text(
                "DELETE FROM solicitacao_documento_itens WHERE solicitacao_id IN "
                "(SELECT id FROM solicitacoes_documentos WHERE client_id = :id)"
            ),
            {"id": cid},
        )
        await db.execute(text("DELETE FROM solicitacoes_documentos WHERE client_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM documents WHERE client_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM fees WHERE client_id = :id"), {"id": cid})
        await db.execute(
            text("DELETE FROM case_movimentos WHERE case_id IN " "(SELECT id FROM cases WHERE client_id = :id)"),
            {"id": cid},
        )
        await db.execute(text("DELETE FROM cases WHERE client_id = :id"), {"id": cid})
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


# ══════════════════════════════════════════════════════════════════════════════
# Caso: detalhe e listagem isolados por client_id
# ══════════════════════════════════════════════════════════════════════════════


async def test_caso_detalhe_e_meus_casos_isolam_por_cliente():
    """Prova: A vê o PRÓPRIO caso (200 com dados); forjar o case_id de B → 404;
    e /meus-casos de A lista só o caso de A (o de B nunca aparece)."""
    from app.core.database import AsyncSessionLocal
    from app.routers.portal import caso_detalhe, meus_casos

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli_a = await _criar_cliente(db, f"Cliente A {tok}")
        cli_b = await _criar_cliente(db, f"Cliente B {tok}")
        ua = await _criar_portal_user(db, cli_a)
        caso_a = await _criar_caso(db, cli_a, f"Caso A {tok}")
        caso_b = await _criar_caso(db, cli_b, f"Caso B {tok}")
        await db.commit()
        try:
            user_a = await _carregar_user(db, ua)

            # POSITIVO: A vê o próprio caso.
            det = await caso_detalhe(case_id=caso_a, db=db, cu=user_a)
            assert det["caso"]["titulo"] == f"Caso A {tok}"

            # IDOR: A forjando o id do caso de B → 404 (WHERE client_id = A).
            with pytest.raises(HTTPException) as exc:
                await caso_detalhe(case_id=caso_b, db=db, cu=user_a)
            assert exc.value.status_code == 404

            # Listagem: só o caso de A.
            ids = {c["id"] for c in (await meus_casos(db=db, cu=user_a))["data"]}
            assert caso_a in ids and caso_b not in ids
        finally:
            await _limpar(db, client_ids=[cli_a, cli_b], user_ids=[ua])


# ══════════════════════════════════════════════════════════════════════════════
# Documentos: só NORMAIS do próprio cliente (nem confidenciais, nem de terceiros)
# ══════════════════════════════════════════════════════════════════════════════


async def test_documentos_portal_apenas_normais_do_proprio_cliente():
    """Prova: A recebe só o próprio documento NORMAL. Não recebe: (a) o próprio
    documento CONFIDENCIAL (filtro de confidencialidade) nem (b) o documento
    normal de B (isolamento por client_id)."""
    from app.core.database import AsyncSessionLocal
    from app.routers.portal import documentos

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli_a = await _criar_cliente(db, f"Cliente A {tok}")
        cli_b = await _criar_cliente(db, f"Cliente B {tok}")
        ua = await _criar_portal_user(db, cli_a)
        doc_a_normal = await _criar_documento(db, cli_a, None, f"A-normal-{tok}", "normal")
        doc_a_conf = await _criar_documento(db, cli_a, None, f"A-conf-{tok}", "confidencial")
        doc_b_normal = await _criar_documento(db, cli_b, None, f"B-normal-{tok}", "normal")
        await db.commit()
        try:
            user_a = await _carregar_user(db, ua)
            ids = {d["id"] for d in (await documentos(db=db, cu=user_a))["data"]}
            assert doc_a_normal in ids  # POSITIVO
            assert doc_a_conf not in ids  # confidencial não vaza p/ portal
            assert doc_b_normal not in ids  # doc de terceiro não vaza
        finally:
            await _limpar(db, client_ids=[cli_a, cli_b], user_ids=[ua])


# ══════════════════════════════════════════════════════════════════════════════
# Financeiro: honorários do próprio cliente
# ══════════════════════════════════════════════════════════════════════════════


async def test_financeiro_portal_apenas_do_proprio_cliente():
    """Prova: A vê o próprio honorário; o de B nunca aparece (isolamento)."""
    from app.core.database import AsyncSessionLocal
    from app.routers.portal import financeiro

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli_a = await _criar_cliente(db, f"Cliente A {tok}")
        cli_b = await _criar_cliente(db, f"Cliente B {tok}")
        ua = await _criar_portal_user(db, cli_a)
        await _criar_fee(db, cli_a, f"Honorario-A-{tok}")
        await _criar_fee(db, cli_b, f"Honorario-B-{tok}")
        await db.commit()
        try:
            user_a = await _carregar_user(db, ua)
            descrs = {f["descricao"] for f in (await financeiro(db=db, cu=user_a))["data"]}
            assert f"Honorario-A-{tok}" in descrs
            assert f"Honorario-B-{tok}" not in descrs
        finally:
            await _limpar(db, client_ids=[cli_a, cli_b], user_ids=[ua])


# ══════════════════════════════════════════════════════════════════════════════
# Mensagens do portal: chat isolado por caso do cliente (leitura E escrita)
# ══════════════════════════════════════════════════════════════════════════════


async def test_mensagens_portal_isola_caso_por_cliente():
    """Prova: A lê o chat do PRÓPRIO caso (200); forjar o caso de B para LER
    (GET) ou ESCREVER (POST) → 404 (_caso_do_cliente). Fecha o IDOR nos dois
    verbos — ler mensagens de outro cliente e injetar mensagem no caso dele."""
    from app.core.database import AsyncSessionLocal
    from app.routers.portal import (
        MsgIn,
        enviar_mensagem_portal,
        listar_mensagens_portal,
    )

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli_a = await _criar_cliente(db, f"Cliente A {tok}")
        cli_b = await _criar_cliente(db, f"Cliente B {tok}")
        adv = await _criar_staff(db, "advogado")
        ua = await _criar_portal_user(db, cli_a)
        caso_a = await _criar_caso(db, cli_a, f"Caso A {tok}", resp_id=adv)
        caso_b = await _criar_caso(db, cli_b, f"Caso B {tok}", resp_id=adv)
        await _inserir_msg_escritorio(db, caso_a, adv, f"ola A {tok}")
        await db.commit()
        try:
            user_a = await _carregar_user(db, ua)

            # POSITIVO: A lê o chat do próprio caso.
            msgs = await listar_mensagens_portal(case_id=caso_a, db=db, cu=user_a)
            assert any(m["mensagem"] == f"ola A {tok}" for m in msgs)

            # IDOR leitura: A no caso de B → 404.
            with pytest.raises(HTTPException) as exc:
                await listar_mensagens_portal(case_id=caso_b, db=db, cu=user_a)
            assert exc.value.status_code == 404

            # IDOR escrita: A injetando mensagem no caso de B → 404.
            with pytest.raises(HTTPException) as exc2:
                await enviar_mensagem_portal(case_id=caso_b, body=MsgIn(mensagem="intruso"), db=db, cu=user_a)
            assert exc2.value.status_code == 404
        finally:
            await _limpar(db, client_ids=[cli_a, cli_b], user_ids=[ua, adv])


# ══════════════════════════════════════════════════════════════════════════════
# Assinaturas: rota LIBERADA ao cliente_externo pelo middleware → isolamento é
# 100% do router. É o ponto mais sensível da allowlist.
# ══════════════════════════════════════════════════════════════════════════════


async def test_signatures_listar_e_assinar_isolam_por_cliente():
    """Prova: em /signatures (rota que o middleware libera ao cliente_externo):
    • listar → A vê só a própria solicitação, nunca a de B;
    • assinar → A assina a PRÓPRIA pendente (200); forjar o id da de B → 404.
    """
    from app.core.database import AsyncSessionLocal
    from app.routers.signatures import assinar, listar

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli_a = await _criar_cliente(db, f"Cliente A {tok}")
        cli_b = await _criar_cliente(db, f"Cliente B {tok}")
        ua = await _criar_portal_user(db, cli_a)
        doc_a = await _criar_documento(db, cli_a, None, f"proc-A-{tok}", "normal")
        doc_b = await _criar_documento(db, cli_b, None, f"proc-B-{tok}", "normal")
        sig_a = await _criar_signature(db, cli_a, doc_a, "pendente")
        sig_b = await _criar_signature(db, cli_b, doc_b, "pendente")
        await db.commit()
        try:
            user_a = await _carregar_user(db, ua)

            # listar: só a solicitação de A.
            ids = {s["id"] for s in (await listar(db=db, cu=user_a))["data"]}
            assert sig_a in ids and sig_b not in ids

            # assinar IDOR: A forjando a solicitação de B → 404 (antes de tocar
            # qualquer evidência; request nem é usado nesse caminho).
            req = types.SimpleNamespace(headers={}, client=None)
            with pytest.raises(HTTPException) as exc:
                await assinar(sig_id=sig_b, request=req, db=db, cu=user_a)
            assert exc.value.status_code == 404

            # assinar POSITIVO: A assina a própria pendente → 200 + comprovante.
            out = await assinar(sig_id=sig_a, request=req, db=db, cu=user_a)
            assert out["comprovante"]["hash_documento"]
        finally:
            await _limpar(db, client_ids=[cli_a, cli_b], user_ids=[ua])


# ══════════════════════════════════════════════════════════════════════════════
# Cross-carteira entre advogados: o chat sigiloso do caso não é lido por
# qualquer membro do escritório — só responsável/auxiliar/gestão (ownership).
# ══════════════════════════════════════════════════════════════════════════════


async def test_mensagens_staff_cross_carteira_exige_ownership():
    """Prova: no lado STAFF do chat (mensagens.py), um advogado SEM vínculo com
    o caso → 403; o responsável passa. Impede um advogado de ler o chat
    cliente↔escritório de caso de OUTRA carteira (IDOR entre advogados)."""
    from app.core.database import AsyncSessionLocal
    from app.routers.mensagens import _verificar_acesso

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db, f"Cliente {tok}")
        resp = await _criar_staff(db, "advogado")
        outro = await _criar_staff(db, "advogado")
        caso = await _criar_caso(db, cli, f"Caso {tok}", resp_id=resp)
        await db.commit()
        try:
            # Responsável passa (sem exceção).
            await _verificar_acesso(caso, await _carregar_user(db, resp), db)

            # Advogado de outra carteira → 403.
            with pytest.raises(HTTPException) as exc:
                await _verificar_acesso(caso, await _carregar_user(db, outro), db)
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[resp, outro])


# ══════════════════════════════════════════════════════════════════════════════
# Solicitações de documentos (upload do cliente): isolamento por client_id
# ══════════════════════════════════════════════════════════════════════════════


async def test_solicitacoes_documentos_isolam_por_cliente():
    """Prova: A lista só as PRÓPRIAS solicitações de documentos; a de B nunca
    aparece (isolamento por client_id no router de upload do portal)."""
    from app.core.database import AsyncSessionLocal
    from app.routers.portal_documentos import listar_solicitacoes_portal

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli_a = await _criar_cliente(db, f"Cliente A {tok}")
        cli_b = await _criar_cliente(db, f"Cliente B {tok}")
        ua = await _criar_portal_user(db, cli_a)
        caso_a = await _criar_caso(db, cli_a, f"Caso A {tok}")
        caso_b = await _criar_caso(db, cli_b, f"Caso B {tok}")
        sol_a = await _criar_solicitacao(db, cli_a, caso_a)
        sol_b = await _criar_solicitacao(db, cli_b, caso_b)
        await db.commit()
        try:
            user_a = await _carregar_user(db, ua)
            ids = {s["id"] for s in (await listar_solicitacoes_portal(db=db, cu=user_a))["data"]}
            assert sol_a in ids and sol_b not in ids
        finally:
            await _limpar(db, client_ids=[cli_a, cli_b], user_ids=[ua])


# ══════════════════════════════════════════════════════════════════════════════
# Movimentos internos: o Portal expõe andamento PROCESSUAL, nunca registro
# interno do escritório (P0-021)
# ══════════════════════════════════════════════════════════════════════════════


async def _criar_movimento(db, case_id: str, tipo: str, descricao: str, dias_atras: int) -> str:
    """Movimento com data_evento controlada — a ordem importa: o teste precisa
    que o movimento INTERNO seja o mais recente, senão `ultima_movimentacao`
    devolveria o oficial por acaso e o teste passaria mesmo sem a correção.

    O intervalo vai por `make_interval(days => :dias)` com um INTEIRO. Com
    `CAST(:dias AS interval)` e a string '3 days', o asyncpg tipa o parâmetro
    como interval e exige um `timedelta` — a string estoura em DataError.
    `make_interval` tem parâmetro tipado int, então não há inferência a errar.
    """
    mov_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO case_movimentos (id, case_id, tipo, descricao, data_evento) "
            "VALUES (:id, :cid, :tipo, :desc, now() - make_interval(days => :dias))"
        ),
        {"id": mov_id, "cid": case_id, "tipo": tipo, "desc": descricao, "dias": int(dias_atras)},
    )
    return mov_id


async def test_portal_nao_expoe_movimentos_internos_nem_chance_de_exito():
    """Regressão P0-021: `case_intel` grava um CaseMovimento tipo="ia" contendo
    "chance≈NN%" — a estimativa de êxito do caso — e o agente de IA grava nota
    livre (tipo="nota"). Antes da correção, portal.caso_detalhe devolvia TODOS
    os movimentos e portal.meus_casos usava o mais recente como
    `ultima_movimentacao`: o cliente lia a própria estimativa de êxito.

    Aqui os dois movimentos internos são os MAIS RECENTES; o oficial é o mais
    antigo. Sem a allowlist, `ultima_movimentacao` seria o de IA e o assert de
    "chance≈" falharia."""
    from app.core.database import AsyncSessionLocal
    from app.routers.portal import caso_detalhe, meus_casos

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db, f"Cliente {tok}")
        uid = await _criar_portal_user(db, cli)
        caso = await _criar_caso(db, cli, f"Caso {tok}")

        oficial = f"Juntada de petição {tok}"
        await _criar_movimento(db, caso, "andamento_oficial", oficial, dias_atras=3)
        await _criar_movimento(
            db, caso, "nota", f"Estratégia interna {tok}: segurar acordo até a perícia.", dias_atras=2
        )
        await _criar_movimento(
            db,
            caso,
            "ia",
            f"IA – Triagem automática {tok}: área≈civil · chance≈78% · complexidade=media. RASCUNHO.",
            dias_atras=1,
        )
        await db.commit()
        try:
            user = await _carregar_user(db, uid)

            # Detalhe: só o andamento processual; nada de IA nem de nota interna.
            det = await caso_detalhe(case_id=caso, db=db, cu=user)
            descricoes = [a["descricao"] for a in det["andamentos"]]
            assert descricoes == [oficial]
            assert not any("chance≈" in d for d in descricoes)
            assert not any("Estratégia interna" in d for d in descricoes)

            # Listagem: a última movimentação visível é a OFICIAL, embora a de
            # IA seja cronologicamente a mais recente.
            caso_listado = next(c for c in (await meus_casos(db=db, cu=user))["data"] if c["id"] == caso)
            assert caso_listado["ultima_movimentacao"]["descricao"] == oficial
        finally:
            await _limpar(db, client_ids=[cli], user_ids=[uid])
