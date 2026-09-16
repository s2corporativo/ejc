"""Impacto regulatório sobre o Banco de Teses (frente 1 do plano de evolução).

O radar já respondia "publicação nova → quais EMPRESAS ela atinge"
(`modules/dpt360/radar_service.py`). Faltava o alvo jurídico: "esta publicação
mexe com a TESE X". Estes testes cobrem as duas camadas:

1. **Serviço** (`services/impacto_regulatorio.py`): funções puras, sem banco.
   O que mais importa aqui é a REGRA DE ALINHAMENTO de área, porque ela é a
   única peça nova — o resto é reuso do radar e do `tese_caso_matcher`.
2. **Endpoint** (`GET /teses/impacto-regulatorio`): exige `RUN_DB_TESTS=1`.
   Cobre RBAC, o gate de visibilidade dos alertas e a janela temporal.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services.impacto_regulatorio import (
    MAX_PUBLICACOES_POR_TESE,
    area_alinhada,
    classificar_publicacao,
    ranquear_teses_afetadas,
)
from app.services.tese_caso_matcher import PESO_AREA, PESO_POR_TERMO, extrair_termos


def _tese_dict(titulo: str, *, area: str | None = None, descricao: str = "",
               tid: str = "t1") -> dict:
    return {"id": tid, "titulo": titulo, "area_juridica": area,
            "termos": extrair_termos(titulo, None, descricao)}


def _pub(titulo: str, *, pid: str = "p1", resumo: str = "",
         keyword: str | None = None) -> dict:
    return {"id": pid, "fonte": "dou", "titulo": titulo, "resumo": resumo,
            "keyword_match": keyword, "link": "https://exemplo.gov.br/x",
            "data_publicacao": "2026-08-20"}


# ── 1. Alinhamento de área — a única regra nova ──────────────────────────────

def test_area_alinha_por_equivalencia_e_nao_por_igualdade():
    """Os dois vocabulários são diferentes de propósito: a publicação é
    classificada como `administrativo` e a tese do escritório vive em
    `licitacoes`. Igualdade de string diria que não batem."""
    assert area_alinhada("administrativo", "licitacoes") is True
    assert area_alinhada("administrativo", "administrativo") is True
    assert area_alinhada("lgpd_ia", "digital_lgpd") is True


def test_area_geral_nao_alinha_com_nada():
    """`geral` é o resultado de nada ter casado — reforçar score com isso seria
    pontuar a ausência de sinal."""
    assert area_alinhada("geral", "civil") is False
    assert area_alinhada("geral", None) is False


def test_area_de_outro_ramo_nao_alinha():
    assert area_alinhada("tributario", "trabalhista") is False
    assert area_alinhada("ambiental", None) is False


def test_classificacao_usa_o_mesmo_classificador_do_radar():
    assert classificar_publicacao(_pub("Instrução Normativa da Receita Federal "
                                       "sobre ICMS")) == "tributario"
    assert classificar_publicacao(_pub("Portaria do IBAMA sobre licenciamento")) == "ambiental"
    assert classificar_publicacao(_pub("Aviso de pauta sem tema jurídico")) == "geral"


# ── 2. Cruzamento publicação × tese ──────────────────────────────────────────

def test_publicacao_que_casa_termos_aponta_a_tese():
    teses = [_tese_dict("Purgação da mora afasta a consolidação da propriedade")]
    pubs = [_pub("Decisão sobre purgação da mora em alienação fiduciária")]
    afetadas = ranquear_teses_afetadas(teses, pubs, piso=25)
    assert len(afetadas) == 1
    assert afetadas[0]["tese_id"] == "t1"
    # Justificativa visível: sem os termos, o score é um número sem lastro.
    assert "purgacao" in afetadas[0]["publicacoes"][0]["termos_casados"]


def test_publicacao_sem_termo_em_comum_nao_aponta_nada():
    teses = [_tese_dict("Purgação da mora na busca e apreensão", area="civil")]
    pubs = [_pub("Portaria sobre horário de funcionamento de repartição")]
    assert ranquear_teses_afetadas(teses, pubs, piso=25) == []


def test_area_alinhada_reforca_o_score_mas_nao_dispara_sozinha():
    """Mesma regra do matcher tese → caso: área é reforço, não gatilho."""
    tese_trab = _tese_dict("Vínculo de emprego em jornada intermitente",
                           area="trabalhista")
    pub_alinhada = _pub("Portaria do Ministério do Trabalho sobre jornada "
                        "intermitente", keyword="trabalho")
    afetadas = ranquear_teses_afetadas([tese_trab], [pub_alinhada], piso=25)
    assert afetadas[0]["publicacoes"][0]["area_alinhada"] is True
    assert afetadas[0]["score_maximo"] >= PESO_POR_TERMO + PESO_AREA

    # Área bate, nenhum termo casa → fora da lista.
    so_area = _pub("Portaria do Ministério do Trabalho sobre outro assunto",
                   keyword="trabalho", pid="p2")
    assert ranquear_teses_afetadas(
        [_tese_dict("Adicional de periculosidade em eletricidade",
                    area="trabalhista")],
        [so_area], piso=25) == []


def test_ordena_por_score_e_desempata_por_id():
    forte = _tese_dict("Purgação da mora e notificação do devedor", tid="b")
    fraca = _tese_dict("Purgação da mora", tid="a")
    igual = _tese_dict("Purgação da mora", tid="A")
    pubs = [_pub("Purgação da mora com notificação do devedor em alienação")]
    afetadas = ranquear_teses_afetadas([fraca, forte, igual], pubs, piso=25)
    assert [t["tese_id"] for t in afetadas][0] == "b"          # maior score
    assert [t["tese_id"] for t in afetadas][1:] == ["A", "a"]  # empate por id


def test_lista_de_publicacoes_por_tese_tem_teto_mas_informa_o_total():
    """Cortar sem dizer que cortou faz "3 publicações" ser lido como "só há 3"."""
    tese = [_tese_dict("Purgação da mora")]
    pubs = [_pub(f"Decisão {i} sobre purgação da mora e alienação", pid=f"p{i:02d}")
            for i in range(MAX_PUBLICACOES_POR_TESE + 4)]
    afetadas = ranquear_teses_afetadas(tese, pubs, piso=25)
    assert len(afetadas[0]["publicacoes"]) == MAX_PUBLICACOES_POR_TESE
    assert afetadas[0]["total_publicacoes"] == MAX_PUBLICACOES_POR_TESE + 4


def test_tese_sem_termos_aproveitaveis_e_ignorada():
    """Título só com stopword não pode casar com tudo."""
    vazia = {"id": "t9", "titulo": "A ação", "area_juridica": "civil", "termos": []}
    assert ranquear_teses_afetadas([vazia], [_pub("Qualquer coisa")], piso=0) == []


def test_sem_publicacao_ou_sem_tese_devolve_lista_vazia():
    assert ranquear_teses_afetadas([], [_pub("x")]) == []
    assert ranquear_teses_afetadas([_tese_dict("Purgação da mora")], []) == []


# ── 3. Endpoint — exige Postgres ─────────────────────────────────────────────

requer_db = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _user(db, role: str = "socio") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Impacto Teste', :role, true)"),
        {"id": uid, "email": f"imp-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _tese_db(db, titulo: str, *, area="civil") -> str:
    tid = str(uuid4())
    await db.execute(
        text("INSERT INTO teses (id, titulo, descricao, area_juridica, tipo, status, "
             "vezes_usada, vezes_venceu, vezes_perdeu) "
             "VALUES (:id, :t, 'Descrição da tese.', :a, 'escritorio', 'ativa', 0, 0, 0)"),
        {"id": tid, "t": titulo, "a": area},
    )
    return tid


async def _alerta(db, titulo: str, *, dias_atras: int = 0,
                  case_id: str | None = None) -> str:
    aid = str(uuid4())
    await db.execute(
        text("INSERT INTO diario_oficial_alertas "
             "(id, fonte, titulo, resumo, link, keyword_match, lido, case_id, created_at) "
             "VALUES (:id, 'dou', :t, :resumo, 'https://exemplo.gov.br', NULL, false, "
             " :case_id, :quando)"),
        # `titulo` é varchar e `resumo` é text: reusar o MESMO parâmetro nos dois
        # faz o asyncpg recusar por tipo ambíguo ("inconsistent types deduced").
        {"id": aid, "t": titulo, "resumo": titulo, "case_id": case_id,
         "quando": datetime.now(timezone.utc) - timedelta(days=dias_atras)},
    )
    return aid


async def _limpar(db, *, tese_ids=(), alerta_ids=(), user_ids=()):
    for tid in tese_ids:
        await db.execute(text("DELETE FROM teses WHERE id = :id"), {"id": tid})
    for aid in alerta_ids:
        await db.execute(text("DELETE FROM diario_oficial_alertas WHERE id = :id"),
                         {"id": aid})
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


@requer_db
async def test_endpoint_aponta_a_tese_atingida_pela_publicacao():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.teses import impacto_regulatorio

    async with AsyncSessionLocal() as db:
        uid = await _user(db)
        alvo = await _tese_db(db, f"Purgação da mora {uuid4().hex[:6]} e alienação fiduciária")
        outra = await _tese_db(db, f"Adicional de insalubridade {uuid4().hex[:6]}",
                               area="trabalhista")
        alerta = await _alerta(db, "Decisão sobre purgação da mora em alienação fiduciária")
        await db.commit()
        try:
            user = await db.get(User, uid)
            r = await impacto_regulatorio(7, 20, 25, db, user)
            atingidas = {t["tese_id"] for t in r["teses_afetadas"]}
            assert alvo in atingidas
            assert outra not in atingidas
            assert r["publicacoes_varridas"] >= 1
            assert "RELER" in r["aviso"]
        finally:
            await _limpar(db, tese_ids=[alvo, outra], alerta_ids=[alerta],
                          user_ids=[uid])


@requer_db
async def test_publicacao_fora_da_janela_nao_entra():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.teses import impacto_regulatorio

    async with AsyncSessionLocal() as db:
        # Isolamento do playground: o varredor limita a 300 publicações por
        # created_at DESC — resíduos de testes anteriores (DJEN/radar, volume
        # variável por run) mais recentes que o alerta-alvo de 40 dias podem
        # estourar o teto e recortá-lo, derrubando a asserção da janela larga
        # de forma intermitente (pipelines #1547/#1550). DB efêmero de CI:
        # remover as publicações mais novas que o alvo é seguro e proporcional.
        await db.execute(text(
            "DELETE FROM diario_oficial_alertas WHERE created_at > NOW() - INTERVAL '39 days'"
        ))
        uid = await _user(db)
        marca = uuid4().hex[:8]
        tese = await _tese_db(db, f"Tese sobre {marca} e consolidação")
        antiga = await _alerta(db, f"Norma sobre {marca} e consolidação", dias_atras=40)
        await db.commit()
        try:
            user = await db.get(User, uid)
            curta = await impacto_regulatorio(7, 20, 25, db, user)
            assert tese not in {t["tese_id"] for t in curta["teses_afetadas"]}

            larga = await impacto_regulatorio(90, 20, 25, db, user)
            assert tese in {t["tese_id"] for t in larga["teses_afetadas"]}
        finally:
            await _limpar(db, tese_ids=[tese], alerta_ids=[antiga], user_ids=[uid])


@requer_db
async def test_advogado_nao_ve_alerta_de_caso_alheio():
    """O gate é o `visible_alerts_query` canônico: alerta preso a caso de outro
    advogado não pode vazar por esta rota — nem o título dele."""
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.teses import impacto_regulatorio

    async with AsyncSessionLocal() as db:
        dono = await _user(db, role="advogado")
        outro = await _user(db, role="advogado")
        cli = str(uuid4())
        await db.execute(
            text("INSERT INTO clients (id, tipo, nome, email, status) "
                 "VALUES (:id, 'PF', :n, :e, 'ativo')"),
            {"id": cli, "n": f"Cliente {cli[:8]}", "e": f"{cli[:8]}@teste.local"},
        )
        caso = str(uuid4())
        await db.execute(
            text("INSERT INTO cases (id, titulo, area, status, client_id, "
                 "advogado_responsavel_id) "
                 "VALUES (:id, 'Caso do outro', 'civil', 'aberto', :cli, :adv)"),
            {"id": caso, "cli": cli, "adv": outro},
        )
        marca = uuid4().hex[:8]
        tese = await _tese_db(db, f"Tese sobre {marca} e consolidação")
        alerta = await _alerta(db, f"Publicação sobre {marca} e consolidação",
                               case_id=caso)
        await db.commit()
        try:
            visitante = await db.get(User, dono)
            r = await impacto_regulatorio(7, 20, 25, db, visitante)
            assert tese not in {t["tese_id"] for t in r["teses_afetadas"]}

            responsavel = await db.get(User, outro)
            r2 = await impacto_regulatorio(7, 20, 25, db, responsavel)
            assert tese in {t["tese_id"] for t in r2["teses_afetadas"]}
        finally:
            await db.execute(text("DELETE FROM diario_oficial_alertas WHERE id = :i"),
                             {"i": alerta})
            await db.execute(text("DELETE FROM cases WHERE id = :i"), {"i": caso})
            await db.execute(text("DELETE FROM clients WHERE id = :i"), {"i": cli})
            await db.commit()
            await _limpar(db, tese_ids=[tese], user_ids=[dono, outro])


@requer_db
async def test_perfil_fora_da_equipe_juridica_recebe_403():
    from app.core.database import AsyncSessionLocal
    from app.models.user import User
    from app.routers.teses import impacto_regulatorio

    async with AsyncSessionLocal() as db:
        uid = await _user(db, role="financeiro")
        await db.commit()
        try:
            user = await db.get(User, uid)
            with pytest.raises(HTTPException) as exc:
                await impacto_regulatorio(7, 20, 25, db, user)
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, user_ids=[uid])
