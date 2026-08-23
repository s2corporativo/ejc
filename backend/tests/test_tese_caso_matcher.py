"""Varredura reversa TESE → CASO (frente 2 do plano de evolução).

O Banco de Teses só sabia responder caso → teses. Estes testes cobrem o
inverso — dada uma tese, onde ela pode caber — em duas camadas:

1. **Matcher** (`services/tese_caso_matcher.py`): funções puras, sem banco,
   rodam em qualquer ambiente.
2. **Endpoint** (`GET /teses/{id}/casos-candidatos`): exige `RUN_DB_TESTS=1`.
   Cobre RBAC, visibilidade por advogado, exclusão de casos já vinculados e
   404 de tese inexistente.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services.tese_caso_matcher import (
    MAX_TERMOS_PONTUADOS,
    PESO_AREA,
    PESO_POR_TERMO,
    extrair_termos,
    normalizar,
    pontuar_texto,
    ranquear_candidatos,
)


# ── 1. Matcher — puro, sem banco ─────────────────────────────────────────────

def test_normalizar_ignora_acento_e_caixa():
    assert normalizar("Purgação da Mora") == "purgacao da mora"
    assert normalizar("BUSCA E APREENSÃO") == "busca e apreensao"
    assert normalizar(None) == ""


def test_extrair_termos_descarta_stopword_curto_e_numero():
    termos = extrair_termos("Ação de busca e apreensão 911", "mora, notificação")
    assert "busca" in termos and "apreensao" in termos
    assert "acao" not in termos       # stopword jurídica
    assert "911" not in termos        # número puro
    assert "de" not in termos         # curto demais


def test_extrair_termos_nao_repete_e_mantem_ordem_estavel():
    a = extrair_termos("purgação mora", "mora purgação")
    b = extrair_termos("purgação mora", "mora purgação")
    assert a == b == ["purgacao", "mora"]


def test_area_sozinha_nao_gera_candidato():
    """Toda tese cível casaria com todo caso cível — isso é ruído, não sinal."""
    score, casados = pontuar_texto(
        ["purgacao"], "Cobrança de aluguel", area_alinhada=True,
    )
    assert score == 0
    assert casados == []     # área alinhada, mas sozinha não pontua


def test_termo_mais_area_pontua_mais_que_termo_sozinho():
    so_termo, _ = pontuar_texto(["purgacao"], "Pedido de purgação da mora")
    com_area, _ = pontuar_texto(
        ["purgacao"], "Pedido de purgação da mora", area_alinhada=True,
    )
    assert so_termo == PESO_POR_TERMO
    assert com_area == PESO_POR_TERMO + PESO_AREA


def test_score_satura_em_cem_e_respeita_teto_de_termos():
    termos = ["alfa", "beta", "gama", "delta", "epsilon", "zeta"]
    texto = "alfa beta gama delta epsilon zeta"
    score, casados = pontuar_texto(termos, texto, area_alinhada=True)
    assert len(casados) == 6                      # relata todos os casados…
    esperado = PESO_POR_TERMO * MAX_TERMOS_PONTUADOS + PESO_AREA
    assert score == min(100, esperado)            # …mas só 4 pontuam


def test_ranquear_ordena_por_score_e_desempata_por_id():
    casos = [
        {"id": "b", "titulo": "purgação da mora", "area": "civil"},
        {"id": "a", "titulo": "purgação da mora", "area": "civil"},
        {"id": "c", "titulo": "purgação da mora e notificação", "area": "civil"},
    ]
    fora = ranquear_candidatos(
        ["purgacao", "notificacao"], casos, area_tese="civil", piso=0,
    )
    assert [c["case_id"] for c in fora] == ["c", "a", "b"]


def test_ranquear_respeita_piso_e_limite():
    casos = [
        {"id": "x", "titulo": "purgação", "area": "civil"},
        {"id": "y", "titulo": "purgação notificação mora", "area": "civil"},
    ]
    # piso alto: só o que casa vários termos entra
    fora = ranquear_candidatos(
        ["purgacao", "notificacao", "mora"], casos, piso=40,
    )
    assert [c["case_id"] for c in fora] == ["y"]

    fora = ranquear_candidatos(["purgacao"], casos, piso=0, limite=1)
    assert len(fora) == 1


def test_ranquear_sem_termos_devolve_vazio():
    """Tese sem termo aproveitável não pode casar com tudo."""
    assert ranquear_candidatos([], [{"id": "a", "titulo": "qualquer"}]) == []


def test_candidato_relata_os_termos_que_casaram():
    """Score sem justificativa convida a confiar sem conferir."""
    fora = ranquear_candidatos(
        ["purgacao", "mora"],
        [{"id": "a", "titulo": "Purgação da mora", "area": "civil"}],
        area_tese="civil", piso=0,
    )
    assert fora[0]["termos_casados"] == ["purgacao", "mora"]
    assert fora[0]["area_coincide"] is True


def test_descricao_dos_fatos_tambem_e_varrida():
    fora = ranquear_candidatos(
        ["purgacao"],
        [{"id": "a", "titulo": "Contrato", "descricao_fatos": "houve purgação da mora"}],
        piso=0,
    )
    assert len(fora) == 1


# ── 2. Endpoint — exige Postgres ─────────────────────────────────────────────

requer_db = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _user(db, role: str = "socio") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Tese Teste', :role, true)"),
        {"id": uid, "email": f"tese-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _cliente(db) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo')"),
        {"id": cid, "nome": f"Cliente {cid[:8]}", "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _caso(db, client_id: str, titulo: str, *, area="civil",
                responsavel: str | None = None) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "advogado_responsavel_id) "
             "VALUES (:id, :titulo, :area, 'aberto', :cid, :resp)"),
        {"id": case_id, "titulo": titulo, "area": area, "cid": client_id,
         "resp": responsavel},
    )
    return case_id


async def _tese(db, titulo: str, *, area="civil", descricao="Descrição da tese.") -> str:
    tid = str(uuid4())
    await db.execute(
        text("INSERT INTO teses (id, titulo, descricao, area_juridica, tipo, status, "
             "vezes_usada, vezes_venceu, vezes_perdeu) "
             "VALUES (:id, :t, :d, :a, 'escritorio', 'ativa', 0, 0, 0)"),
        {"id": tid, "t": titulo, "d": descricao, "a": area},
    )
    return tid


async def _limpar(db, *, tese_ids=(), case_ids=(), client_ids=(), user_ids=()):
    for tid in tese_ids:
        await db.execute(text("DELETE FROM tese_caso_links WHERE tese_id = :id"), {"id": tid})
        await db.execute(text("DELETE FROM teses WHERE id = :id"), {"id": tid})
    for cid in case_ids:
        await db.execute(text("DELETE FROM tese_caso_links WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM cases WHERE client_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    if os.getenv("RUN_DB_TESTS"):
        from app.core.database import engine
        await engine.dispose()


@requer_db
async def test_varredura_acha_o_caso_aderente_e_ignora_o_alheio():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.teses import casos_candidatos

    async with AsyncSessionLocal() as db:
        uid = await _user(db)
        cli = await _cliente(db)
        aderente = await _caso(db, cli, "Busca e apreensão com purgação da mora")
        alheio = await _caso(db, cli, "Cobrança de aluguel residencial")
        tese = await _tese(db, "Purgação da mora na busca e apreensão")
        await db.commit()
        try:
            user = await db.get(User, uid)
            r = await casos_candidatos(tese, 20, 25, False, db, user)
            ids = [c["case_id"] for c in r["candidatos"]]
            assert aderente in ids
            assert alheio not in ids
            # A resposta explica POR QUE casou.
            achado = next(c for c in r["candidatos"] if c["case_id"] == aderente)
            assert achado["termos_casados"]
        finally:
            await _limpar(db, tese_ids=[tese], case_ids=[aderente, alheio],
                          client_ids=[cli], user_ids=[uid])


@requer_db
async def test_caso_ja_vinculado_sai_da_lista():
    """O pedido é 'onde ela AINDA pode caber'."""
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.teses import casos_candidatos

    async with AsyncSessionLocal() as db:
        uid = await _user(db)
        cli = await _cliente(db)
        caso = await _caso(db, cli, "Busca e apreensão com purgação da mora")
        tese = await _tese(db, "Purgação da mora na busca e apreensão")
        await db.execute(
            text("INSERT INTO tese_caso_links (id, tese_id, case_id) "
                 "VALUES (:id, :t, :c)"),
            {"id": str(uuid4()), "t": tese, "c": caso},
        )
        await db.commit()
        try:
            user = await db.get(User, uid)
            r = await casos_candidatos(tese, 20, 25, False, db, user)
            assert caso not in [c["case_id"] for c in r["candidatos"]]
        finally:
            await _limpar(db, tese_ids=[tese], case_ids=[caso],
                          client_ids=[cli], user_ids=[uid])


@requer_db
async def test_advogado_so_ve_os_proprios_casos_na_varredura():
    """Sem o filtro de visibilidade a varredura vazaria título e área de casos
    que o usuário não pode abrir."""
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.teses import casos_candidatos

    async with AsyncSessionLocal() as db:
        dono = await _user(db, role="advogado")
        outro = await _user(db, role="advogado")
        cli = await _cliente(db)
        meu = await _caso(db, cli, "Busca e apreensão com purgação da mora",
                          responsavel=dono)
        alheio = await _caso(db, cli, "Purgação da mora em contrato alheio",
                             responsavel=outro)
        tese = await _tese(db, "Purgação da mora na busca e apreensão")
        await db.commit()
        try:
            user = await db.get(User, dono)
            r = await casos_candidatos(tese, 20, 25, False, db, user)
            ids = [c["case_id"] for c in r["candidatos"]]
            assert meu in ids
            assert alheio not in ids
        finally:
            await _limpar(db, tese_ids=[tese], case_ids=[meu, alheio],
                          client_ids=[cli], user_ids=[dono, outro])


@requer_db
async def test_perfil_fora_da_equipe_juridica_recebe_403():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.teses import casos_candidatos

    async with AsyncSessionLocal() as db:
        uid = await _user(db, role="financeiro")
        tese = await _tese(db, "Purgação da mora")
        await db.commit()
        try:
            user = await db.get(User, uid)
            with pytest.raises(HTTPException) as exc:
                await casos_candidatos(tese, 20, 25, False, db, user)
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, tese_ids=[tese], user_ids=[uid])


@requer_db
async def test_tese_inexistente_da_404():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.teses import casos_candidatos

    async with AsyncSessionLocal() as db:
        uid = await _user(db)
        await db.commit()
        try:
            user = await db.get(User, uid)
            with pytest.raises(HTTPException) as exc:
                await casos_candidatos(str(uuid4()), 20, 25, False, db, user)
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, user_ids=[uid])
