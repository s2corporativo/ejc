"""Integridade de contadores, status e visibilidade de dependentes — DB-level.

Reproduz (Fase 0) e trava (PR 1) os defeitos de "falso positivo" do EJC:

A. `pecas_aguardando_revisao` do Dashboard responde 0 porque exclui `rascunho`,
   justamente o estado em que a IA deixa a peça recém-gerada.
B. `ativos` do Dashboard (`total - encerrado`) conta caso `arquivado` como ativo,
   divergindo de `/cases/stats` (`total - encerrado - arquivado`) e da listagem.
C. `?status=<valor fora do enum>` chega cru ao Postgres (coluna é ENUM nativo
   `casestatus`) e estoura InvalidTextRepresentation → 500, em vez de 422.
D. Soft-delete de caso não propaga: peças/prazos/documentos do caso excluído
   continuam visíveis em listagens e métricas operacionais.

Padrão da suíte: Postgres real, `AsyncSessionLocal`, handlers do router chamados
diretamente, mesmo gate de CI dos demais *_dblevel.py. Sem Postgres, pula —
nunca conecta em produção.

As contagens do Dashboard são GLOBAIS (não escopadas ao fixture), por isso todas
as asserções aqui são sobre DELTA (depois - antes), nunca sobre valor absoluto.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


# ── fixtures de dados ────────────────────────────────────────────────────────

async def _criar_cliente(db, client_id):
    await db.execute(
        text(
            "INSERT INTO clients (id, tipo, nome, email, status) "
            "VALUES (:id, 'PF', 'Cliente Integridade', :email, 'ativo')"
        ),
        {"id": client_id, "email": f"{client_id[:8]}@teste.local"},
    )


async def _criar_admin(db) -> str:
    """Executor com role 'admin': é gestão, logo NÃO sofre `_filtro_visibilidade`
    — é exatamente o perfil em que os falsos positivos aparecem."""
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Admin Integridade', 'admin', true)"
        ),
        {"id": uid, "email": f"admin-{uid[:8]}@teste.local"},
    )
    return uid


async def _criar_caso(db, case_id, client_id, status="aberto", deleted=False):
    await db.execute(
        text(
            "INSERT INTO cases (id, titulo, area, status, client_id, deleted_at) "
            "VALUES (:id, 'Caso Integridade', 'civil', :status, :cid, :del)"
        ),
        {
            "id": case_id,
            "status": status,
            "cid": client_id,
            "del": datetime.now(timezone.utc) if deleted else None,
        },
    )


async def _criar_peca(db, case_id, status="rascunho", ai=True, revisada=False):
    peca_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO legal_docs (id, titulo, tipo_peca, status, conteudo, "
            "ai_generated, human_reviewed, case_id) "
            "VALUES (:id, 'Peça Integridade', 'peticao_inicial', :st, '# minuta', "
            ":ai, :rev, :cid)"
        ),
        {"id": peca_id, "st": status, "ai": ai, "rev": revisada, "cid": case_id},
    )
    return peca_id


async def _carregar_user(db, uid):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, client_id, case_ids, user_id):
    for cid in case_ids:
        await db.execute(text("DELETE FROM legal_docs WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM deadlines WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM documents WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM case_movimentos WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": user_id})
    await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


@pytest.fixture(autouse=True)
def _dashboard_sem_cache():
    """O Dashboard tem cache in-process de 30s sem invalidação por escrita
    (`routers/dashboard.py`). Sem limpar, um teste serve o resultado do anterior."""
    from app.routers.dashboard import _dashboard_cache
    _dashboard_cache.clear()
    yield
    _dashboard_cache.clear()


async def _dashboard(db, cu) -> dict:
    from app.routers.dashboard import _dashboard_cache, dashboard
    _dashboard_cache.clear()
    return await dashboard(db=db, cu=cu)


# ── B. contadores de casos ───────────────────────────────────────────────────

async def test_caso_em_triagem_conta_como_ativo():
    """Triagem é caso em curso: entra em `ativos` no Dashboard e em /cases/stats."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import stats_casos

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            antes_dash = (await _dashboard(db, cu))["casos"]["ativos"]
            antes_stats = (await stats_casos(advogado_id=None, db=db, cu=cu))["ativos"]

            await _criar_caso(db, case_id, client_id, status="aberto")
            await db.commit()

            depois_dash = (await _dashboard(db, cu))["casos"]["ativos"]
            depois_stats = (await stats_casos(advogado_id=None, db=db, cu=cu))["ativos"]

            assert depois_dash - antes_dash == 1, "caso em triagem deve contar como ativo no Dashboard"
            assert depois_stats - antes_stats == 1, "caso em triagem deve contar como ativo em /cases/stats"
        finally:
            await _limpar(db, client_id, [case_id], uid)


async def test_caso_arquivado_nao_conta_como_ativo_no_dashboard():
    """REPRODUZ DEFEITO B: `ativos = total - encerrado` inclui `arquivado`."""
    from app.core.database import AsyncSessionLocal

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            antes = (await _dashboard(db, cu))["casos"]
            await _criar_caso(db, case_id, client_id, status="arquivado")
            await db.commit()
            depois = (await _dashboard(db, cu))["casos"]

            assert depois["total"] - antes["total"] == 1, "arquivado entra no total"
            assert depois["ativos"] - antes["ativos"] == 0, (
                "caso ARQUIVADO não pode ser contado como ativo"
            )
        finally:
            await _limpar(db, client_id, [case_id], uid)


async def test_caso_excluido_nao_conta_em_lugar_nenhum():
    """Soft-delete some de total, ativos e arquivados."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import stats_casos

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            antes_dash = (await _dashboard(db, cu))["casos"]
            antes_stats = await stats_casos(advogado_id=None, db=db, cu=cu)

            await _criar_caso(db, case_id, client_id, status="aberto", deleted=True)
            await db.commit()

            depois_dash = (await _dashboard(db, cu))["casos"]
            depois_stats = await stats_casos(advogado_id=None, db=db, cu=cu)

            assert depois_dash["total"] == antes_dash["total"]
            assert depois_dash["ativos"] == antes_dash["ativos"]
            assert depois_stats["total"] == antes_stats["total"]
            assert depois_stats["ativos"] == antes_stats["ativos"]
        finally:
            await _limpar(db, client_id, [case_id], uid)


async def test_dashboard_e_listagem_usam_a_mesma_definicao_de_ativo():
    """REPRODUZ DEFEITO B: Dashboard e /cases/stats discordam com um arquivado."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import stats_casos

    client_id = str(uuid4())
    ids = [str(uuid4()) for _ in range(9)]
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            d0 = (await _dashboard(db, cu))["casos"]["ativos"]
            s0 = (await stats_casos(advogado_id=None, db=db, cu=cu))["ativos"]

            # Cenário exato da auditoria: 8 abertos (ex-"triagem", migration
            # 126) + 1 arquivado.
            for cid in ids[:8]:
                await _criar_caso(db, cid, client_id, status="aberto")
            await _criar_caso(db, ids[8], client_id, status="arquivado")
            await db.commit()

            d1 = (await _dashboard(db, cu))["casos"]["ativos"]
            s1 = (await stats_casos(advogado_id=None, db=db, cu=cu))["ativos"]

            assert d1 - d0 == 8, "Dashboard deve contar 8 ativos (o arquivado não conta)"
            assert s1 - s0 == 8, "/cases/stats deve contar 8 ativos"
            assert d1 - d0 == s1 - s0, "Dashboard e listagem devem compartilhar a definição"
        finally:
            await _limpar(db, client_id, ids, uid)


# ── C. filtro de status ──────────────────────────────────────────────────────

async def test_status_invalido_retorna_422_e_nao_500():
    """REPRODUZ DEFEITO C: 'all' chega cru ao ENUM nativo → 500.

    Hoje levanta DBAPIError (InvalidTextRepresentation) e o handler global de
    `main.py` converte em 500. O esperado é 422 de domínio, informando os
    valores válidos.
    """
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import listar

    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            with pytest.raises(HTTPException) as exc:
                await listar(
                    page=1, page_size=20, search=None, area=None,
                    status_f="all", arquivo="todos", advogado_id=None, db=db, cu=cu,
                )
            assert exc.value.status_code == 422
            # A mensagem precisa dizer o que é aceito, senão o cliente fica cego.
            assert "aberto" in str(exc.value.detail)
        finally:
            # A transação abortou no erro do enum: precisa de rollback antes de limpar.
            await db.rollback()
            await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
            await db.commit()


async def test_filtro_todos_e_a_ausencia_do_parametro():
    """"Todos" é a AUSÊNCIA do filtro — nunca um valor artificial no banco."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import listar

    client_id = str(uuid4())
    ids = [str(uuid4()) for _ in range(3)]
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        for cid, st in zip(ids, ["aberto", "em_instrucao", "arquivado"]):
            await _criar_caso(db, cid, client_id, status=st)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            r = await listar(
                page=1, page_size=500, search=None, area=None,
                status_f=None, arquivo="todos", advogado_id=None, db=db, cu=cu,
            )
            devolvidos = {c.id for c in r["data"]}
            assert set(ids).issubset(devolvidos), (
                "sem filtro de status, arquivo=todos deve devolver os três estados"
            )
        finally:
            await _limpar(db, client_id, ids, uid)


async def test_status_valido_continua_funcionando():
    """Guarda de regressão: os 6 valores do enum seguem aceitos."""
    from app.core.database import AsyncSessionLocal
    from app.models.case import CaseStatus
    from app.routers.cases import listar

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="em_producao")
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            for st in [s.value for s in CaseStatus]:
                r = await listar(
                    page=1, page_size=500, search=None, area=None,
                    status_f=st, arquivo="todos", advogado_id=None, db=db, cu=cu,
                )
                assert isinstance(r["total"], int)
            r = await listar(
                page=1, page_size=500, search=None, area=None,
                status_f="em_producao", arquivo="todos", advogado_id=None, db=db, cu=cu,
            )
            assert case_id in {c.id for c in r["data"]}
        finally:
            await _limpar(db, client_id, [case_id], uid)


# ── A + D. peças, revisão e visibilidade de dependentes ──────────────────────

async def test_peca_em_rascunho_conta_como_aguardando_revisao():
    """REPRODUZ DEFEITO A: `status NOT IN ('rascunho')` zera o contador.

    A pergunta operacional é "quantas peças ativas ainda precisam de revisão
    humana?" — e a IA entrega a peça justamente em `rascunho`.
    """
    from app.core.database import AsyncSessionLocal

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="aberto")
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            antes = (await _dashboard(db, cu))["pecas_aguardando_revisao"]
            for _ in range(22):
                await _criar_peca(db, case_id, status="rascunho", ai=True, revisada=False)
            await _criar_peca(db, case_id, status="aprovada", ai=True, revisada=True)
            await db.commit()

            depois = (await _dashboard(db, cu))["pecas_aguardando_revisao"]
            assert depois - antes == 22, (
                "22 peças de IA em rascunho e não revisadas devem aparecer na fila"
            )
        finally:
            await _limpar(db, client_id, [case_id], uid)


async def test_peca_de_caso_excluido_nao_conta_nas_metricas():
    """REPRODUZ DEFEITO D: soft-delete do caso não retira a peça das métricas."""
    from app.core.database import AsyncSessionLocal

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="aberto", deleted=True)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            antes = (await _dashboard(db, cu))["pecas_aguardando_revisao"]
            for _ in range(3):
                await _criar_peca(db, case_id, status="rascunho", ai=True, revisada=False)
            await db.commit()
            depois = (await _dashboard(db, cu))["pecas_aguardando_revisao"]

            assert depois == antes, (
                "peça de caso EXCLUÍDO não pode aparecer em métrica operacional"
            )
        finally:
            await _limpar(db, client_id, [case_id], uid)


async def test_peca_de_caso_ativo_aparece_na_listagem_operacional():
    """Guarda de regressão do lado positivo: caso vivo → peça visível."""
    from app.core.database import AsyncSessionLocal
    from app.routers.legal_docs import listar as listar_docs

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="aberto")
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            peca_id = await _criar_peca(db, case_id, status="rascunho")
            await db.commit()
            r = await listar_docs(
                page=1, page_size=500, case_id=None, status_f=None, db=db, cu=cu,
            )
            assert peca_id in {d["id"] for d in r["data"]}
        finally:
            await _limpar(db, client_id, [case_id], uid)


async def test_peca_de_caso_excluido_some_da_listagem_operacional():
    """REPRODUZ DEFEITO D: para GESTÃO a peça órfã continua listada.

    `legal_docs.py` só filtra por casos visíveis quando o usuário NÃO é gestão —
    admin/sócio enxergam a peça de um caso já excluído.
    """
    from app.core.database import AsyncSessionLocal
    from app.routers.legal_docs import listar as listar_docs

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="aberto", deleted=True)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            peca_id = await _criar_peca(db, case_id, status="rascunho")
            await db.commit()
            r = await listar_docs(
                page=1, page_size=500, case_id=None, status_f=None, db=db, cu=cu,
            )
            assert peca_id not in {d["id"] for d in r["data"]}, (
                "peça de caso excluído não pode aparecer na listagem operacional"
            )
        finally:
            await _limpar(db, client_id, [case_id], uid)


async def test_restauracao_do_caso_restabelece_visibilidade_da_peca():
    """Restaurar o caso devolve a peça às listagens — sem tocar na peça."""
    from app.core.database import AsyncSessionLocal
    from app.routers.legal_docs import listar as listar_docs

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="aberto", deleted=True)
        await db.commit()
        cu = await _carregar_user(db, uid)
        try:
            peca_id = await _criar_peca(db, case_id, status="rascunho")
            await db.commit()

            r = await listar_docs(page=1, page_size=500, case_id=None,
                                  status_f=None, db=db, cu=cu)
            assert peca_id not in {d["id"] for d in r["data"]}

            # Restaura o caso (lixeira) — a peça nunca foi tocada.
            await db.execute(
                text("UPDATE cases SET deleted_at = NULL WHERE id = :id"), {"id": case_id}
            )
            await db.commit()

            r2 = await listar_docs(page=1, page_size=500, case_id=None,
                                   status_f=None, db=db, cu=cu)
            assert peca_id in {d["id"] for d in r2["data"]}, (
                "restaurar o caso deve restabelecer a visibilidade dos dependentes"
            )
        finally:
            await _limpar(db, client_id, [case_id], uid)


# ── F. diagnóstico de integridade (somente leitura) ──────────────────────────

async def test_diagnostico_detecta_peca_de_caso_excluido():
    """REPRODUZ DEFEITO F: não há diagnóstico de integridade observável."""
    from app.core.database import AsyncSessionLocal
    from app.services.integridade_service import diagnosticar_integridade

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="aberto", deleted=True)
        await db.commit()
        try:
            peca_id = await _criar_peca(db, case_id, status="rascunho")
            await db.commit()

            rel = await diagnosticar_integridade(db)
            achados = {a["tipo"]: a for a in rel["achados"]}
            alvo = achados["peca_de_caso_excluido"]

            assert alvo["total"] >= 1
            assert peca_id in alvo["ids"]
            assert alvo["entidade_pai"] == "cases"
            assert alvo["estado_pai"] == "excluido"
            assert alvo["acao_recomendada"]
        finally:
            await _limpar(db, client_id, [case_id], uid)


async def test_diagnostico_nao_marca_documento_em_triagem_como_orfao():
    """Documento sem `case_id` é estado LEGÍTIMO (caixa de entrada/GED)."""
    from app.core.database import AsyncSessionLocal
    from app.services.integridade_service import diagnosticar_integridade

    client_id, doc_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await db.commit()
        try:
            await db.execute(
                text(
                    "INSERT INTO documents (id, titulo, filename, filepath, "
                    "confidencialidade, client_id, uploaded_by) "
                    "VALUES (:id, 'Contrato triagem', 'contrato.pdf', '/tmp/x.pdf', "
                    "'normal', :cid, :uid)"
                ),
                {"id": doc_id, "cid": client_id, "uid": uid},
            )
            await db.commit()

            rel = await diagnosticar_integridade(db)
            achados = {a["tipo"]: a for a in rel["achados"]}
            invalidos = achados.get("documento_orfao_invalido", {"ids": []})
            assert doc_id not in invalidos["ids"], (
                "documento sem caso, mas com cliente, é triagem legítima — não é órfão inválido"
            )
        finally:
            await db.execute(text("DELETE FROM documents WHERE id = :id"), {"id": doc_id})
            await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
            await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
            await db.commit()


async def test_diagnostico_nao_altera_dados():
    """O diagnóstico é SOMENTE LEITURA: nada muda depois de rodar."""
    from app.core.database import AsyncSessionLocal
    from app.services.integridade_service import diagnosticar_integridade

    client_id, case_id = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        uid = await _criar_admin(db)
        await _criar_cliente(db, client_id)
        await _criar_caso(db, case_id, client_id, status="aberto", deleted=True)
        await db.commit()
        try:
            peca_id = await _criar_peca(db, case_id, status="rascunho")
            await db.commit()

            await diagnosticar_integridade(db)

            peca = (await db.execute(
                text("SELECT deleted_at, case_id, status FROM legal_docs WHERE id = :id"),
                {"id": peca_id},
            )).one()
            assert peca[0] is None, "diagnóstico não pode excluir peça"
            assert peca[1] == case_id, "diagnóstico não pode desvincular peça"

            caso = (await db.execute(
                text("SELECT deleted_at FROM cases WHERE id = :id"), {"id": case_id}
            )).scalar_one()
            assert caso is not None, "diagnóstico não pode restaurar caso"
        finally:
            await _limpar(db, client_id, [case_id], uid)
