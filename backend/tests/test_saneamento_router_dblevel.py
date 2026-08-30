"""Rotas de /api/saneamento/* contra Postgres real (migration 154 aplicada).

Contrato coberto:
  - RBAC: `advogado_auxiliar` lê, mas não decide nem aplica dedup — só
    `advogado`/`socio`/`admin`/`superadmin` (regra inegociável: sinaliza,
    quem decide é sempre um advogado, nunca um job/estagiário).
  - ESCOPO POR TITULARIDADE DE CASO (achado ALTO da auditoria de segurança):
    `advogado`/`advogado_auxiliar` só decide/aplica/lista o que pertence a um
    caso em que atua (responsável/auxiliar) ou caso órfão; `socio`+ vê e age
    em qualquer caso. numero_cnj sem caso correspondente no sistema é negado
    à equipe.
  - `POST /indicativos/{id}/decidir`: grava decisao+decidido_por+decidido_em
    e recusa decidir de novo o mesmo indicativo (409) — mesmo sob corrida
    (UPDATE condicionado ao estado, não um SELECT solto antes).
  - `POST /duplicatas/{id}/aplicar`: recusa aplicar `multi_grau`/
    `conexo_sugerido` (essas nunca são fundidas) e exige `confirmar=true`.
  - `GET /divergencias`: esconde o tipo `SIGILO` de quem não é gestão.
  - `GET /tpu/cobertura`: reflete a semente da migration (código 246).

O `AuthMiddleware` global do EJC decodifica o JWT ele mesmo, ANTES da injeção
de dependências — `dependency_overrides[get_current_user]` não o atravessa
(diferente de chamar o handler do router direto, como os *_dblevel.py de
agenda_eventos fazem). Por isso cada teste usa um Bearer token real, gerado
com o mesmo `create_access_token` que o login produz, sobre um usuário
efetivamente inserido em `users` (FK de audit_logs.user_id exige linha real).

Sem RUN_DB_TESTS=1, pula (mesmo padrão dos demais *_dblevel.py).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

_pg = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)

NUM_CNJ_OFICIAL = "00008323520184013202"
NUM_CNJ_OUTRO = "00009995220184013202"
API = "/api/saneamento"


async def _criar_user(db, role: str) -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Saneamento Teste', :role, true)"),
        {"id": uid, "email": f"san-{uid[:8]}@teste.local", "role": role},
    )
    await db.commit()
    return uid


async def _criar_cliente(db) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', 'Cliente Saneamento Teste', :email, 'ativo')"),
        {"id": cid, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(
    db, client_id: str, numero_processo: str | None, resp_id: str | None,
) -> str:
    """Caso com `numero_processo` = numero_cnj mascarado (formato que
    Case.numero_processo aceita) — o router compara por dígitos.
    `numero_processo=None` cria um caso SEM o espelho legado, para testar o
    vínculo exclusivamente via `Process.numero_cnj` (achado de revisão de
    código: processo acessório não fica só no espelho)."""
    case_id = str(uuid4())
    mascarado = None
    if numero_processo is not None:
        mascarado = (
            f"{numero_processo[0:7]}-{numero_processo[7:9]}.{numero_processo[9:13]}."
            f"{numero_processo[13:14]}.{numero_processo[14:16]}.{numero_processo[16:20]}"
        )
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, numero_processo, "
             "advogado_responsavel_id) VALUES "
             "(:id, 'Caso saneamento teste', 'civil', 'em_instrucao', :cid, :np, :resp)"),
        {"id": case_id, "cid": client_id, "np": mascarado, "resp": resp_id},
    )
    return case_id


async def _criar_processo(db, case_id: str, numero_cnj: str) -> None:
    """Processo (principal ou acessório) vinculado ao caso — fonte canônica
    de numero_cnj (app/models/process.py), distinta do espelho legado
    `Case.numero_processo`."""
    await db.execute(
        text("INSERT INTO processes (case_id, numero_cnj) VALUES (:cid, :cnj)"),
        {"cid": case_id, "cnj": numero_cnj},
    )


def _token_para(uid: str, role: str) -> dict[str, str]:
    from app.core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token(uid, role)}"}


async def _limpar(db, *, case_ids=(), client_ids=()):
    """Limpa as tabelas do módulo + casos/clientes de teste. `audit_logs` é
    WORM (Issue #582) — não apagável por teste — e `users` referenciado por
    FK de audit_logs criado nesta rodada; deixar as linhas de teste (usuário/
    log) no banco descartável local é inofensivo e evita violar a
    imutabilidade ou a FK."""
    for numero in (NUM_CNJ_OFICIAL, NUM_CNJ_OUTRO):
        await db.execute(text("DELETE FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
                          {"n": numero})
        await db.execute(text("DELETE FROM saneamento_plano_dedup WHERE numero_cnj = :n"),
                          {"n": numero})
        await db.execute(text("DELETE FROM saneamento_divergencia WHERE numero_cnj = :n"),
                          {"n": numero})
    for cid in case_ids:
        await db.execute(text("DELETE FROM processes WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


def _client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@_pg
async def test_leitor_nao_pode_decidir_indicativo():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado_auxiliar")
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, true, 'alta')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        ind_id = (await db.execute(
            text("SELECT id FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    try:
        resp = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "teste"},
            headers=_token_para(uid, "advogado_auxiliar"),
        )
        assert resp.status_code == 403
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db)


@_pg
async def test_advogado_responsavel_decide_e_segunda_decisao_e_recusada():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, NUM_CNJ_OFICIAL, resp_id=uid)
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, true, 'alta')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        ind_id = (await db.execute(
            text("SELECT id FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    headers = _token_para(uid, "advogado")
    try:
        resp1 = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "silêncio de 400 dias"},
            headers=headers,
        )
        assert resp1.status_code == 200, resp1.text
        body = resp1.json()
        assert body["decisao"] == "encerrar"
        assert body["decidido_por"] == uid

        resp2 = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "manter_ativo", "justificativa": "segunda tentativa"},
            headers=headers,
        )
        assert resp2.status_code == 409
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_advogado_sem_vinculo_ao_caso_nao_pode_decidir():
    """Achado ALTO da auditoria: advogado sem vínculo com o caso não pode
    decidir encerramento de processo alheio."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        responsavel = await _criar_user(db, "advogado")
        estranho = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, NUM_CNJ_OFICIAL, resp_id=responsavel)
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, true, 'alta')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        ind_id = (await db.execute(
            text("SELECT id FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    try:
        resp = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "teste"},
            headers=_token_para(estranho, "advogado"),
        )
        assert resp.status_code == 403

        # Confirma que o indicativo NÃO foi decidido (a tentativa negada não
        # deixou rastro na coluna decisao).
        ainda_pendente = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "responsável de verdade"},
            headers=_token_para(responsavel, "advogado"),
        )
        assert ainda_pendente.status_code == 200, ainda_pendente.text
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_advogado_nao_pode_decidir_caso_orfao():
    """Achado de revisão de código: caso ÓRFÃO (sem responsável nem
    auxiliar) é escrita restrita à gestão — mesma regra de
    app/core/ownership.py::verificar_acesso_caso. Uma versão anterior deste
    router liberava caso órfão para qualquer advogado, reabrindo a brecha
    que aquele gate já fecha para o resto do EJC."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        qualquer_advogado = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, NUM_CNJ_OFICIAL, resp_id=None)  # órfão
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, true, 'alta')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        ind_id = (await db.execute(
            text("SELECT id FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    try:
        negado = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "teste"},
            headers=_token_para(qualquer_advogado, "advogado"),
        )
        assert negado.status_code == 403

        permitido = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "gestão assume o caso órfão"},
            headers=_token_para(socio, "socio"),
        )
        assert permitido.status_code == 200, permitido.text
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_socio_decide_qualquer_caso_mesmo_sem_vinculo():
    """Gestão (socio+) tem visão/ação firm-wide — não é restrita a vínculo."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        responsavel = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, NUM_CNJ_OFICIAL, resp_id=responsavel)
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, true, 'alta')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        ind_id = (await db.execute(
            text("SELECT id FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    try:
        resp = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "teste"},
            headers=_token_para(socio, "socio"),
        )
        assert resp.status_code == 200, resp.text
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_listagem_de_indicativos_filtra_por_titularidade_do_caso():
    """Achado ALTO: as rotas GET também escopam por caso — advogado sem
    vínculo não vê o indicativo de um processo alheio na listagem."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        responsavel = await _criar_user(db, "advogado")
        estranho = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, NUM_CNJ_OFICIAL, resp_id=responsavel)
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, true, 'alta')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()

    try:
        vista_responsavel = _client().get(
            f"{API}/indicativos", headers=_token_para(responsavel, "advogado"),
        )
        assert vista_responsavel.status_code == 200
        assert any(i["numero_cnj"] == NUM_CNJ_OFICIAL for i in vista_responsavel.json())

        vista_estranho = _client().get(
            f"{API}/indicativos", headers=_token_para(estranho, "advogado"),
        )
        assert vista_estranho.status_code == 200
        assert not any(i["numero_cnj"] == NUM_CNJ_OFICIAL for i in vista_estranho.json())
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_divergencia_sigilo_e_escondida_de_quem_nao_tem_visao_de_relatorio():
    """Achado MÉDIO (auditoria) + achado de revisão de código: nivelSigilo>0
    é tratamento restrito — não deve aparecer no relatório amplo de quem não
    tem visão de relatório firm-wide (`pode_ver_todos`, admin+ — limiar mais
    alto que `is_gestao`/socio+, que é só o gate de ESCRITA)."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        admin = await _criar_user(db, "admin")
        await db.execute(
            text("INSERT INTO saneamento_divergencia (numero_cnj, tipo) VALUES (:n, 'sigilo')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()

    try:
        vista_advogado = _client().get(f"{API}/divergencias", headers=_token_para(adv, "advogado"))
        assert vista_advogado.status_code == 200
        assert not any(d["tipo"] == "sigilo" for d in vista_advogado.json())

        vista_admin = _client().get(f"{API}/divergencias", headers=_token_para(admin, "admin"))
        assert vista_admin.status_code == 200
        assert any(d["tipo"] == "sigilo" for d in vista_admin.json())
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db)


@_pg
async def test_socio_nao_admin_nao_ve_lista_firm_wide_mas_decide_qualquer_caso():
    """Achado de revisão de código: `_filtro_escopo_caso` (leitura) exige
    `pode_ver_todos` (admin+), não `is_gestao` (socio+) — socio sem vínculo
    ao caso não vê o indicativo na LISTAGEM, mas ainda pode DECIDIR sobre
    ele (gate de escrita continua em is_gestao/socio+, ver
    test_socio_decide_qualquer_caso_mesmo_sem_vinculo)."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        responsavel = await _criar_user(db, "advogado")
        socio = await _criar_user(db, "socio")
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, NUM_CNJ_OFICIAL, resp_id=responsavel)
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, true, 'alta')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()

    try:
        vista_socio = _client().get(f"{API}/indicativos", headers=_token_para(socio, "socio"))
        assert vista_socio.status_code == 200
        assert not any(i["numero_cnj"] == NUM_CNJ_OFICIAL for i in vista_socio.json())
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_aplicar_dedup_recusa_multi_grau_e_exige_confirmacao():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, NUM_CNJ_OFICIAL, resp_id=uid)
        await db.execute(
            text("INSERT INTO saneamento_plano_dedup "
                 "(numero_cnj, id_interno_principal, ids_absorvidos, tipo) "
                 "VALUES (:n, 'p1', ARRAY['p2'], 'multi_grau')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        plano_id = (await db.execute(
            text("SELECT id FROM saneamento_plano_dedup WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    headers = _token_para(uid, "advogado")
    try:
        sem_confirmar = _client().post(
            f"{API}/duplicatas/{plano_id}/aplicar", json={"confirmar": False}, headers=headers,
        )
        assert sem_confirmar.status_code == 422

        multi_grau = _client().post(
            f"{API}/duplicatas/{plano_id}/aplicar", json={"confirmar": True}, headers=headers,
        )
        assert multi_grau.status_code == 422
        assert "multi_grau" in multi_grau.text or "nunca" in multi_grau.text
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_cobertura_tpu_reflete_semente_da_migration():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado_auxiliar")

    try:
        resp = _client().get(f"{API}/tpu/cobertura", headers=_token_para(uid, "advogado_auxiliar"))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 1
        assert body["classificados"] >= 1  # código 246, semeado pela migration
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db)


@_pg
async def test_advogado_nao_acessa_excecoes_mas_socio_acessa():
    """Achado de revisão de código: numero_bruto/numero_corrigido
    identificam processo mesmo antes de validados e não dá para escopar por
    caso com segurança (numero_corrigido é NULL na maior parte das linhas
    pendentes) — a rota inteira fica restrita a socio+."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db, "advogado")
        aux = await _criar_user(db, "advogado_auxiliar")
        socio = await _criar_user(db, "socio")

    negado_adv = _client().get(f"{API}/excecoes", headers=_token_para(adv, "advogado"))
    assert negado_adv.status_code == 403
    negado_aux = _client().get(f"{API}/excecoes", headers=_token_para(aux, "advogado_auxiliar"))
    assert negado_aux.status_code == 403
    permitido = _client().get(f"{API}/excecoes", headers=_token_para(socio, "socio"))
    assert permitido.status_code == 200, permitido.text


@_pg
async def test_decisao_encerrar_rejeitada_quando_indicativo_nao_e_candidato():
    """Achado de revisão de código: avaliar_encerramento() persiste
    indicativos NÃO candidatos (ex.: reativador posterior, silêncio
    insuficiente) para histórico — decidir 'encerrar' sobre um deles
    contorna a própria avaliação automática que diz não encerrar."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, NUM_CNJ_OFICIAL, resp_id=uid)
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, false, 'baixa')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        ind_id = (await db.execute(
            text("SELECT id FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    try:
        negado = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "tentando contornar a avaliação"},
            headers=_token_para(uid, "advogado"),
        )
        assert negado.status_code == 422

        permitido = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "manter_ativo", "justificativa": "confirma que não é candidato"},
            headers=_token_para(uid, "advogado"),
        )
        assert permitido.status_code == 200, permitido.text
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_justificativa_so_espaco_e_rejeitada():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, NUM_CNJ_OFICIAL, resp_id=uid)
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, true, 'alta')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        ind_id = (await db.execute(
            text("SELECT id FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    try:
        resp = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "   "},
            headers=_token_para(uid, "advogado"),
        )
        assert resp.status_code == 422
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_vinculo_via_processo_acessorio_sem_espelho_legado():
    """Achado de revisão de código: processo acessório (recurso, cautelar…)
    tem numero_cnj só na tabela canônica `processes`, NUNCA espelhado em
    `Case.numero_processo` (que reflete só o processo principal). O advogado
    do caso precisa continuar decidindo sobre o acessório."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado")
        cli = await _criar_cliente(db)
        # numero_processo=None: caso SEM espelho legado — só o Process abaixo
        # liga este caso ao numero_cnj do acessório.
        caso = await _criar_caso(db, cli, None, resp_id=uid)
        await _criar_processo(db, caso, NUM_CNJ_OFICIAL)
        await db.execute(
            text("INSERT INTO saneamento_indicativo_encerramento "
                 "(numero_cnj, candidato, confianca) VALUES (:n, true, 'alta')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        ind_id = (await db.execute(
            text("SELECT id FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    try:
        resp = _client().post(
            f"{API}/indicativos/{ind_id}/decidir",
            json={"decisao": "encerrar", "justificativa": "acessório resolvido via Process"},
            headers=_token_para(uid, "advogado"),
        )
        assert resp.status_code == 200, resp.text
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_aplicar_dedup_exige_vinculo_com_todos_os_casos_do_numero():
    """Achado de revisão de código: quando o MESMO numero_cnj casa com mais
    de um Case (o próprio cenário de duplicata real ainda não fundida), só
    ter vínculo com UM deles não basta — .first() escolhia um caso
    arbitrário. Aqui dois casos distintos compartilham o mesmo numero_cnj
    via Process; só quem tem vínculo com AMBOS pode aplicar."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        dono_unico = await _criar_user(db, "advogado")  # só liga a um dos dois
        cli = await _criar_cliente(db)
        caso_a = await _criar_caso(db, cli, None, resp_id=dono_unico)
        caso_b = await _criar_caso(db, cli, None, resp_id=None)  # órfão — outro dono
        await _criar_processo(db, caso_a, NUM_CNJ_OFICIAL)
        await _criar_processo(db, caso_b, NUM_CNJ_OFICIAL)
        await db.execute(
            text("INSERT INTO saneamento_plano_dedup "
                 "(numero_cnj, id_interno_principal, ids_absorvidos, tipo) "
                 "VALUES (:n, 'p1', ARRAY['p2'], 'duplicata')"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        plano_id = (await db.execute(
            text("SELECT id FROM saneamento_plano_dedup WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar_one()

    try:
        # dono_unico só está vinculado ao caso_a; caso_b é órfão (só gestão
        # decide) — vínculo parcial não basta.
        negado = _client().post(
            f"{API}/duplicatas/{plano_id}/aplicar",
            json={"confirmar": True},
            headers=_token_para(dono_unico, "advogado"),
        )
        assert negado.status_code == 403
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso_a, caso_b], client_ids=[cli])
