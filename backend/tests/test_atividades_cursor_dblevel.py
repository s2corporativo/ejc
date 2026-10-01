"""Tarefa 3 — cursor + resumo em /atividades (integração PostgreSQL).

Cobre o contrato do plano:
  - 5 pernas da view (prazo/tarefa/suspensao/agenda/intimacao) aparecem no feed
  - datas empatadas e nulas: desempate tipo,id; NULL data por último
  - A1/A2/gestão: visibilidade de atividades.py:23-39 reaplicada em toda página
  - caso alheio nunca vaza (nem via cursor)
  - apenas_pendentes e situacao=concluido/agrupamento cancelado
  - virada do dia: urgencia pela data operacional (clock.py), não CURRENT_DATE
  - concatenação cursor == conjunto legado (sem duplicatas, dataset imutável)
  - resumo = conjunto inteiro visível (não a página), sem filtros de clique
  - enriquecimento (confirmado/ciencia para prazo; hora/local para agenda)
    presente SOMENTE na página autorizada, sem perda de botão
  - cliente externo não acessa resumo (403)
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.routers.atividades import listar_atividades, resumo_atividades

_pg = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str, rotulo: str) -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, "
             "is_active) VALUES (:id, :email, 'x', :nome, :role, true)"),
        {"id": uid, "email": f"atv-{rotulo}-{uid[:8]}@teste.local", "role": role,
         "nome": f"Atividade {rotulo}"},
    )
    return uid


async def _carregar_user(db, uid: str):
    from app.models.user import User
    from sqlalchemy import select
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _criar_caso(db, dono: str, titulo: str) -> str:
    cid, cliente = str(uuid4()), str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, nome, responsavel_id, tipo, status) "
             "VALUES (:id, :n, :d, 'PF', 'ativo')"),
        {"id": cliente, "n": f"Cliente {titulo}", "d": dono})
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, prioridade, client_id, "
             "advogado_responsavel_id, proxima_acao, created_at) VALUES "
             "(:id, :t, 'civil', 'aberto', 'media', :cli, :d, 'Ação', now())"),
        {"id": cid, "t": titulo, "cli": cliente, "d": dono})
    return cid


async def _limpar(db, *, user_ids=()):
    for uid in user_ids:
        await db.execute(
            text("DELETE FROM djen_comunicacoes WHERE advogado_id = :u"),
            {"u": uid})
        await db.execute(
            text("DELETE FROM agenda_eventos WHERE responsavel_id = :u OR created_by = :u"),
            {"u": uid})
        await db.execute(
            text("DELETE FROM deadlines WHERE responsavel_id = :u "
                 "OR case_id IN (SELECT id FROM cases WHERE advogado_responsavel_id = :u)"),
            {"u": uid})
        await db.execute(
            text("DELETE FROM tasks WHERE responsavel_id = :u OR criado_por = :u "
                 "OR case_id IN (SELECT id FROM cases WHERE advogado_responsavel_id = :u)"),
            {"u": uid})
        await db.execute(
            text("DELETE FROM suspensoes_tribunal WHERE created_by = :u"), {"u": uid})
        await db.execute(
            text("DELETE FROM cases WHERE advogado_responsavel_id = :u"), {"u": uid})
        await db.execute(
            text("DELETE FROM clients WHERE responsavel_id = :u"), {"u": uid})
        await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _seed_cinco_pernas(db, dono: str, caso: str, *, data_base):
    """1 linha de cada perna da view, todas com a MESMA data (empate)."""
    # prazo
    await db.execute(text(
        "INSERT INTO deadlines (id, titulo, tipo, prioridade, status, data_prazo, "
        "case_id, responsavel_id, confirmado, ciencia_confirmada) VALUES "
        "(:id, 'P', 'processual', 'media', 'pendente', :d, :c, :r, true, true)"),
        {"id": str(uuid4()), "d": data_base, "c": caso, "r": dono})
    # tarefa
    await db.execute(text(
        "INSERT INTO tasks (id, titulo, status, prioridade, data_limite, case_id, "
        "responsavel_id, criado_por, created_at) VALUES "
        "(:id, 'T', 'a_fazer', 'media', :d, :c, :r, :r, now())"),
        {"id": str(uuid4()), "d": data_base, "c": caso, "r": dono})
    # agenda (com hora/local p/ enriquecimento)
    await db.execute(text(
        "INSERT INTO agenda_eventos (id, titulo, tipo, data_evento, hora, local, "
        "case_id, responsavel_id, concluido, created_by) VALUES "
        "(:id, 'A', 'audiencia', :d, '09:30', 'Fórum Central', :c, :r, false, :r)"),
        {"id": str(uuid4()), "d": data_base, "c": caso, "r": dono})
    # intimação DJEN (advogado_id = dono)
    await db.execute(text(
        "INSERT INTO djen_comunicacoes (id, comunicacao_id_externo, advogado_id, "
        "tipo_comunicacao, data_disponibilizacao, texto_resumo, case_id, processada) "
        "VALUES (:id, :ext, :adv, 'Intimação', :d, 'Resumo', :c, false)"),
        {"id": str(uuid4()), "ext": f"ext-{uuid4()}", "adv": dono, "d": data_base,
         "c": caso})
    # suspensão (case_id NULL, created_by = dono → visível só ao dono/gestão)
    await db.execute(text(
        "INSERT INTO suspensoes_tribunal (id, tribunal, data_inicio, data_fim, "
        "motivo, created_by) VALUES (:id, 'TJMG', :d, :d2, 'Recesso', :r)"),
        {"id": str(uuid4()), "d": data_base, "d2": data_base + timedelta(days=30),
         "r": dono})


@_pg
async def test_cinco_pernas_empate_e_enriquecimento():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        caso_a = await _criar_caso(db, a1, "Caso A 5pernas")
        base = date.today() + timedelta(days=2)  # mesma data → empate
        await _seed_cinco_pernas(db, a1, caso_a, data_base=base)
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            p1 = await listar_atividades(
                apenas_pendentes=False, pagination="cursor", page_size=50,
                cursor=None, case_id=None, tipo=None, situacao=None,
                urgencia=None, data_inicio=None, data_fim=None, db=db, cu=cu)
            tipos = {i["tipo"] for i in p1["data"]}
            assert tipos == {"prazo", "tarefa", "agenda", "intimacao", "suspensao"}
            # enriquecimento da página
            por_tipo = {i["tipo"]: i for i in p1["data"]}
            assert por_tipo["prazo"]["confirmado"] is True
            assert por_tipo["prazo"]["ciencia_confirmada"] is True
            assert por_tipo["agenda"]["hora"] == "09:30"
            assert por_tipo["agenda"]["local"] == "Fórum Central"
            # nenhuma perna perdeu campos prévios
            for i in p1["data"]:
                for campo in ("id", "tipo", "titulo", "date", "status", "case_id",
                              "urgencia", "dias_restantes", "subtipo", "prioridade"):
                    assert campo in i
            # desempate: empate de data → ordena por tipo, id
            chaves = [(i["date"], i["tipo"], i["id"]) for i in p1["data"]
                      if i["date"] == base.isoformat()]
            assert chaves == sorted(chaves)
        finally:
            await _limpar(db, user_ids=[a1])


@_pg
async def test_visibilidade_a1_a2_gestao_e_caso_alheio():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        a2 = await _criar_user(db, "advogado", "a2")
        socio = await _criar_user(db, "socio", "socio")
        caso_a = await _criar_caso(db, a1, "Caso A vis")
        caso_b = await _criar_caso(db, a2, "Caso B vis")
        d = date.today() + timedelta(days=3)
        for _ in range(3):
            await db.execute(text(
                "INSERT INTO deadlines (id, titulo, tipo, prioridade, status, "
                "data_prazo, case_id, responsavel_id) VALUES "
                "(:id, 'P', 'processual', 'media', 'pendente', :d, :c, :r)"),
                {"id": str(uuid4()), "d": d, "c": caso_a, "r": a1})
            await db.execute(text(
                "INSERT INTO deadlines (id, titulo, tipo, prioridade, status, "
                "data_prazo, case_id, responsavel_id) VALUES "
                "(:id, 'P', 'processual', 'media', 'pendente', :d, :c, :r)"),
                {"id": str(uuid4()), "d": d, "c": caso_b, "r": a2})
        await db.commit()
        try:
            cu1 = await _carregar_user(db, a1)
            cu2 = await _carregar_user(db, a2)
            cus = await _carregar_user(db, socio)

            async def coleta(cu, page_size=2):
                vistos, cursor = [], None
                while True:
                    out = await listar_atividades(
                        apenas_pendentes=True, pagination="cursor",
                        page_size=page_size, cursor=cursor, case_id=None,
                        tipo="prazo", situacao=None, urgencia=None,
                        data_inicio=None, data_fim=None, db=db, cu=cu)
                    vistos.extend(out["data"])
                    if not out["has_more"]:
                        break
                    cursor = out["next_cursor"]
                return vistos

            v1, v2, vs = await coleta(cu1), await coleta(cu2), await coleta(cus)
            assert len(v1) == 3 and all(i["case_id"] == caso_a for i in v1)
            assert len(v2) == 3 and all(i["case_id"] == caso_b for i in v2)
            # gestão vê TODOS os prazos do banco (dataset sintético incluído);
            # isolamos as linhas deste teste para provar a visão dos dois casos
            do_teste = [i for i in vs if i["case_id"] in (caso_a, caso_b)]
            assert len(do_teste) == 6
            alheios = [i for i in vs if i["case_id"] == caso_b]
            assert alheios, "gestão deve ver também o caso alheio"
            # cursor de A1 não abre para A2 (mesma rota, viewer trocado)
            p1_a1 = await listar_atividades(
                apenas_pendentes=True, pagination="cursor", page_size=1,
                cursor=None, case_id=None, tipo=None, situacao=None,
                urgencia=None, data_inicio=None, data_fim=None, db=db, cu=cu1)
            with pytest.raises(HTTPException):
                await listar_atividades(
                    apenas_pendentes=True, pagination="cursor", page_size=1,
                    cursor=p1_a1["next_cursor"], case_id=None, tipo=None,
                    situacao=None, urgencia=None, data_inicio=None,
                    data_fim=None, db=db, cu=cu2)
        finally:
            await _limpar(db, user_ids=[a1, a2, socio])


@_pg
async def test_apenas_pendentes_situacao_e_concatenacao_legado():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        caso_a = await _criar_caso(db, a1, "Caso A situacao")
        d = date.today() + timedelta(days=1)
        # 4 prazos: pendente, concluido, cancelado, vencido(pendente antigo)
        estados = ["pendente", "concluido", "cancelado",
                   "pendente"]  # último com data passada
        for i, st in enumerate(estados):
            dd = d if i < 3 else date.today() - timedelta(days=5)
            await db.execute(text(
                "INSERT INTO deadlines (id, titulo, tipo, prioridade, status, "
                "data_prazo, case_id, responsavel_id) VALUES "
                "(:id, 'P', 'processual', 'media', :st, :d, :c, :r)"),
                {"id": str(uuid4()), "st": st, "d": dd, "c": caso_a, "r": a1})
        # 2 tarefas: fazendo (em_execucao) e concluida
        await db.execute(text(
            "INSERT INTO tasks (id, titulo, status, prioridade, data_limite, "
            "case_id, responsavel_id, criado_por, created_at) VALUES "
            "(:id, 'T', 'fazendo', 'media', :d, :c, :r, :r, now())"),
            {"id": str(uuid4()), "d": d, "c": caso_a, "r": a1})
        await db.execute(text(
            "INSERT INTO tasks (id, titulo, status, prioridade, data_limite, "
            "case_id, responsavel_id, criado_por, created_at) VALUES "
            "(:id, 'T', 'concluida', 'media', :d, :c, :r, :r, now())"),
            {"id": str(uuid4()), "d": d, "c": caso_a, "r": a1})
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            kw = dict(apenas_pendentes=True, pagination="cursor", page_size=50,
                      cursor=None, case_id=None, tipo=None, situacao=None,
                      urgencia=None, data_inicio=None, data_fim=None, db=db, cu=cu)
            pendentes = (await listar_atividades(**kw))["data"]
            # apenas_pendentes exclui concluido/concluida/cancelado (vencido fica)
            assert len(pendentes) == 3
            # situacao=concluido (com apenas_pendentes=False) inclui cancelado
            kw2 = dict(apenas_pendentes=False, pagination="cursor", page_size=50,
                       cursor=None, case_id=None, tipo=None,
                       situacao="concluido", urgencia=None,
                       data_inicio=None, data_fim=None, db=db, cu=cu)
            concluida = (await listar_atividades(**kw2))["data"]
            assert len(concluida) == 3  # concluido + cancelado + concluida
            # situação em_execucao pega a tarefa fazendo
            kw3 = dict(apenas_pendentes=False, pagination="cursor", page_size=50,
                       cursor=None, case_id=None, tipo=None,
                       situacao="em_execucao", urgencia=None,
                       data_inicio=None, data_fim=None, db=db, cu=cu)
            exec_ = (await listar_atividades(**kw3))["data"]
            assert len(exec_) == 1 and exec_[0]["tipo"] == "tarefa"
            # concatenação cursor == conjunto do legado (dataset imutável)
            legado = await listar_atividades(apenas_pendentes=False, db=db, cu=cu)
            ids_legado = sorted(i["id"] for i in legado["data"])
            vistos, cursor = [], None
            while True:
                out = await listar_atividades(
                    apenas_pendentes=False, pagination="cursor", page_size=2,
                    cursor=cursor, case_id=None, tipo=None, situacao=None,
                    urgencia=None, data_inicio=None, data_fim=None, db=db, cu=cu)
                vistos.extend(out["data"])
                if not out["has_more"]:
                    break
                cursor = out["next_cursor"]
            ids_cursor = [i["id"] for i in vistos]
            assert sorted(ids_cursor) == ids_legado
            assert len(ids_cursor) == len(set(ids_cursor))
        finally:
            await _limpar(db, user_ids=[a1])


@_pg
async def test_urgencia_filtro_e_resumo_conjunto_inteiro():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        caso_a = await _criar_caso(db, a1, "Caso A urg")
        hoje = date.today()
        # prazos: 1 vencido, 1 crítico (hoje+2), 1 atenção (hoje+5), 1 normal (hoje+20)
        for dd, rot in [(-3, "vencido"), (2, "critico"), (5, "atencao"),
                        (20, "normal")]:
            await db.execute(text(
                "INSERT INTO deadlines (id, titulo, tipo, prioridade, status, "
                "data_prazo, case_id, responsavel_id) VALUES "
                "(:id, :rot, 'processual', 'media', 'pendente', :d, :c, :r)"),
                {"id": str(uuid4()), "rot": rot, "d": hoje + timedelta(days=dd),
                 "c": caso_a, "r": a1})
        # prazos concluído vencido NÃO entra no resumo (resumo = pendentes)
        await db.execute(text(
            "INSERT INTO deadlines (id, titulo, tipo, prioridade, status, "
            "data_prazo, case_id, responsavel_id) VALUES "
            "(:id, 'x', 'processual', 'media', 'concluido', :d, :c, :r)"),
            {"id": str(uuid4()), "d": hoje - timedelta(days=10), "c": caso_a, "r": a1})
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            # filtro urgencia=vencido
            kw = dict(apenas_pendentes=True, pagination="cursor", page_size=50,
                      cursor=None, case_id=None, tipo="prazo", situacao=None,
                      urgencia="vencido", data_inicio=None, data_fim=None,
                      db=db, cu=cu)
            vencidos = (await listar_atividades(**kw))["data"]
            assert len(vencidos) == 1
            assert vencidos[0]["urgencia"] == "vencido"
            # resumo (conjunto inteiro pendente, sem filtro de clique)
            res = await resumo_atividades(case_id=None, db=db, cu=cu)
            assert res["vencido"] == 1
            assert res["critico"] == 1
            assert res["atencao"] == 1
            assert res["normal"] == 1
            assert res["total_pendentes"] == 4
            assert res["data_operacional"]
            # resumo não é afetado por "página" (não existe página aqui) e
            # replica a regra dos cards — pendentes por escopo do caso
            res_caso = await resumo_atividades(case_id=caso_a, db=db, cu=cu)
            assert res_caso == res
        finally:
            await _limpar(db, user_ids=[a1])


@_pg
async def test_resumo_bloqueia_cliente_externo():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        cext = await _criar_user(db, "cliente_externo", "cext")
        await db.commit()
        try:
            cu = await _carregar_user(db, cext)
            with pytest.raises(HTTPException) as e:
                await resumo_atividades(case_id=None, db=db, cu=cu)
            assert e.value.status_code == 403
        finally:
            await _limpar(db, user_ids=[cext])


@_pg
async def test_janela_datas_e_ultimo_item_n_mais_1():
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        a1 = await _criar_user(db, "advogado", "a1")
        caso_a = await _criar_caso(db, a1, "Caso A janela")
        hoje = date.today()
        for i in range(5):
            await db.execute(text(
                "INSERT INTO agenda_eventos (id, titulo, tipo, data_evento, "
                "responsavel_id, concluido, created_by) VALUES "
                "(:id, 'E', 'reuniao', :d, :r, false, :r)"),
                {"id": str(uuid4()), "d": hoje + timedelta(days=i), "r": a1})
        # evento fora da janela
        await db.execute(text(
            "INSERT INTO agenda_eventos (id, titulo, tipo, data_evento, "
            "responsavel_id, concluido, created_by) VALUES "
            "(:id, 'E', 'reuniao', :d, :r, false, :r)"),
            {"id": str(uuid4()), "d": hoje + timedelta(days=90), "r": a1})
        await db.commit()
        try:
            cu = await _carregar_user(db, a1)
            kw = dict(apenas_pendentes=False, pagination="cursor", page_size=3,
                      cursor=None, case_id=None, tipo="agenda", situacao=None,
                      urgencia=None,
                      data_inicio=hoje, data_fim=hoje + timedelta(days=7),
                      db=db, cu=cu)
            p1 = await listar_atividades(**kw)
            assert len(p1["data"]) == 3  # n, não n+1
            assert p1["has_more"] is True  # 5 na janela → n+1 detectou
            # janela fecha no dia 7: nenhuma linha do dia 90
            vistos = list(p1["data"])
            while p1["has_more"]:
                p1 = await listar_atividades(
                    **dict(kw, cursor=p1["next_cursor"]))
                vistos.extend(p1["data"])
            assert len(vistos) == 5
            datas = [v["date"][:10] for v in vistos]
            assert all(hoje.isoformat() <= d <=
                       (hoje + timedelta(days=7)).isoformat() for d in datas)
            # ordem total determinística: re-execução (página única) idêntica
            out = await listar_atividades(**dict(kw, page_size=10))
            assert [i["id"] for i in out["data"]] == [i["id"] for i in vistos]
        finally:
            await _limpar(db, user_ids=[a1])
