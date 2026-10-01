"""Regressão DB-level do cockpit Hoje — GET /api/dashboard/hoje (Tarefa 4).

Prova os gates com PostgreSQL real:
  • contadores EXATOS sobre a carteira inteira (não amostra do navegador);
  • sem cross-user: prazos/casos de B nunca aparecem para A;
  • decisões <=3, prioridades não-crescentes, peças (120/112) acima de
    prazo vencido (118);
  • socio vê escopo escritório; advogado vê só a carteira;
  • /api/dashboard/ segue intacto (shape com 'casos' e 'degradado').
Requer ``RUN_DB_TESTS=1`` — **SKIP não é PASS** (baseline §6.4).
"""
from __future__ import annotations

import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid5, NAMESPACE_URL

import pytest
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.routers.dashboard import dashboard, dashboard_hoje

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL com migrations (RUN_DB_TESTS=1) — SKIP não é PASS",
)

NS = uuid5(NAMESPACE_URL, "perf.dashboard.hoje.test")
HOJE = None  # resolvido no seed (date)


def uid(chave: str) -> str:
    return str(uuid5(NS, chave))


A = uid("user:A")
B = uid("user:B")
S = uid("user:S")
CID = uid("client")


def _user(uid_: str, role: str):
    return SimpleNamespace(id=uid_, role=SimpleNamespace(value=role))


async def _semear() -> None:
    from datetime import date

    global HOJE
    HOJE = date.today()
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active)"
            " VALUES (:id, :email, 'x', 'Perf Hoje', :role::userrole, true)"
            " ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": A, "email": f"{A}@dbtest.local", "role": "advogado"},
            {"id": B, "email": f"{B}@dbtest.local", "role": "advogado"},
            {"id": S, "email": f"{S}@dbtest.local", "role": "socio"},
        ])
        await db.execute(text(
            "INSERT INTO clients (id, tipo, nome, email, status, responsavel_id)"
            " VALUES (:id, 'PF', 'Cliente Hoje', 'hoje@dbtest.local', 'ativo', :resp)"
            " ON CONFLICT (id) DO NOTHING"
        ), {"id": CID, "resp": A})

        # 25 casos na carteira A (20 aberto + 3 em_instrucao + 2 encerrado)
        # e 10 na carteira B (todos abertos) → ativos A = 23, B = 10.
        casos = []
        for i in range(25):
            status = "aberto" if i < 20 else (
                "em_instrucao" if i < 23 else "encerrado")
            casos.append({
                "id": uid(f"case:A{i}"), "titulo": f"Caso Hoje A{i:02d}",
                "status": status, "resp": A,
            })
        for i in range(10):
            casos.append({
                "id": uid(f"case:B{i}"), "titulo": f"Caso Hoje B{i:02d}",
                "status": "aberto", "resp": B,
            })
        # risco para decisões: 1 crítico em A
        casos.append({
            "id": uid("case:riscoA"), "titulo": "Caso Risco A",
            "status": "aberto", "resp": A,
        })
        await db.execute(text(
            "INSERT INTO cases (id, titulo, area, status, client_id,"
            " advogado_responsavel_id, proxima_acao, risco)"
            " VALUES (:id, :titulo, 'civil', :status::casestatus, :cid,"
            " :resp, 'Atuar', CASE WHEN :id = :riscoA THEN 'critico' END)"
            " ON CONFLICT (id) DO NOTHING"
        ), [{**c, "cid": CID, "riscoA": uid("case:riscoA")} for c in casos])

        # Prazos: 1 vencido, 1 hoje, 1 em 2 dias (carteira A); 1 vencido (B)
        await db.execute(text(
            "INSERT INTO deadlines (id, titulo, tipo, prioridade, status,"
            " data_prazo, case_id, responsavel_id, confirmado)"
            " VALUES (:id, :t, 'processual', 'media', 'pendente'::deadlinestatus,"
            " :dp, :case_id, :resp, true) ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": uid("dl:vencido"), "t": "Prazo vencido hoje A",
             "dp": HOJE - timedelta(days=1), "case_id": uid("case:A0"), "resp": A},
            {"id": uid("dl:hoje"), "t": "Prazo de hoje A",
             "dp": HOJE, "case_id": uid("case:A1"), "resp": A},
            {"id": uid("dl:2d"), "t": "Prazo em 2 dias A",
             "dp": HOJE + timedelta(days=2), "case_id": uid("case:A2"), "resp": A},
            {"id": uid("dl:Bvenc"), "t": "Prazo vencido B",
             "dp": HOJE - timedelta(days=3), "case_id": uid("case:B0"), "resp": B},
        ])

        # Tarefas "minhas" de A: 1 vencida urgente (score 130), 1 sem data
        await db.execute(text(
            "INSERT INTO tasks (id, titulo, status, prioridade, data_limite,"
            " case_id, responsavel_id, criado_por)"
            " VALUES (:id, :t, 'a_fazer'::taskstatus, :pr, :dl, :case_id,"
            " :resp, :resp) ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": uid("tk:vencida"), "t": "Tarefa urgente vencida",
             "pr": "urgente", "dl": HOJE - timedelta(days=1),
             "case_id": uid("case:A3"), "resp": A},
            {"id": uid("tk:semdata"), "t": "Tarefa sem data",
             "pr": "media", "dl": None, "case_id": None, "resp": A},
        ])

        # Peças HITL: 2 em_revisao (caseless) + 1 corrigida (case A)
        await db.execute(text(
            "INSERT INTO legal_docs (id, titulo, tipo_peca, status, case_id,"
            " conteudo, ai_generated, human_reviewed)"
            " VALUES (:id, :t, 'peticao_inicial', :st::pecastatus, :case_id,"
            " '# p', true, false) ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": uid("ld:r1"), "t": "Peça revisão 1", "st": "em_revisao",
             "case_id": None},
            {"id": uid("ld:r2"), "t": "Peça revisão 2", "st": "em_revisao",
             "case_id": None},
            {"id": uid("ld:c1"), "t": "Peça corrigida 1", "st": "corrigida",
             "case_id": uid("case:A4")},
        ])

        # Documentos 7d: 2 na carteira A, 1 na B, 1 antigo
        await db.execute(text(
            "INSERT INTO documents (id, titulo, filename, filepath,"
            " confidencialidade, case_id, uploaded_by, created_at, updated_at)"
            " VALUES (:id, :t, :fn, :fp, 'normal'::docconfidencialidade,"
            " :case_id, :up, now(), now()) ON CONFLICT (id) DO NOTHING"
        ), [
            {"id": uid("doc:A0"), "t": "Doc A0", "fn": "a0.pdf", "fp": "/p/a0.pdf",
             "case_id": uid("case:A0"), "up": A},
            {"id": uid("doc:A1"), "t": "Doc A1", "fn": "a1.pdf", "fp": "/p/a1.pdf",
             "case_id": uid("case:A1"), "up": A},
            {"id": uid("doc:B0"), "t": "Doc B0", "fn": "b0.pdf", "fp": "/p/b0.pdf",
             "case_id": uid("case:B0"), "up": B},
            {"id": uid("doc:old"), "t": "Doc antigo", "fn": "o.pdf", "fp": "/p/o.pdf",
             "case_id": uid("case:A2"), "up": A},
        ])
        # 'Doc antigo' com created_at fora da janela de 7 dias
        await db.execute(text(
            "UPDATE documents SET created_at = now() - interval '30 days'"
            " WHERE id = :i"
        ), {"i": uid("doc:old")})
        await db.commit()


@pytest.mark.asyncio
async def test_advogado_ve_somente_a_carteira_com_contagens_exatas():
    await _semear()
    async with AsyncSessionLocal() as db:
        r = await dashboard_hoje(db=db, cu=_user(A, "advogado"))
    c = r["contadores"]
    assert r["degradado"] == []
    assert c["casos_ativos"] == 23  # 20 aberto + 3 em_instrucao (exclui 2 encerrados)
    assert c["casos_total"] == 26   # + caso do risco
    assert c["prazos_vencidos"] == 1
    assert c["prazos_hoje"] == 1
    assert c["prazos_proximos_3d"] == 1
    assert c["tarefas_hoje_minhas"] == 2
    assert c["documentos_7d"] == 2  # docs de B e o antigo ficam fora
    assert c["pecas_aguardando_revisao"] >= 3
    assert r["escopos"]["casos"] == "carteira"
    # decisões: <=3, prioridades não-crescentes, peça (120) antes do prazo vencido (118)
    d = r["decisoes"]
    assert 1 <= len(d) <= 3
    prios = [x["prioridade"] for x in d]
    assert prios == sorted(prios, reverse=True)
    assert d[0]["prioridade"] == 120
    assert any(x["id"].startswith("prazo-vencido") for x in d) or len(d) == 3
    assert all(x["id"].startswith("peca-") or x["id"].startswith("prazo-")
               or x["id"].startswith("tarefa-") or x["id"].startswith("risco-")
               for x in d)


@pytest.mark.asyncio
async def test_sem_cross_user_entre_advogados():
    await _semear()
    async with AsyncSessionLocal() as db:
        rB = await dashboard_hoje(db=db, cu=_user(B, "advogado"))
    c = rB["contadores"]
    assert c["casos_ativos"] == 10
    assert c["prazos_vencidos"] == 1  # só o próprio prazo de B
    assert c["documentos_7d"] == 1
    # nenhum título do caso de A vaza nas decisões de B
    titulos = " ".join(x["detalhe"] for x in rB["decisoes"])
    assert "Caso Hoje A" not in titulos
    assert "Prazo vencido hoje A" not in titulos


@pytest.mark.asyncio
async def test_socio_ve_escopo_escritorio():
    await _semear()
    async with AsyncSessionLocal() as db:
        r = await dashboard_hoje(db=db, cu=_user(S, "socio"))
    assert r["escopos"]["casos"] == "escritorio"
    assert r["contadores"]["casos_ativos"] >= 33  # 23 de A + 10 de B
    assert r["contadores"]["prazos_vencidos"] == 2


@pytest.mark.asyncio
async def test_dashboard_kpi_legado_intacto():
    """GET / (KPIs executivos) mantém shape — o Hoje não o substitui."""
    await _semear()
    async with AsyncSessionLocal() as db:
        r = await dashboard(db=db, cu=_user(S, "socio"))
    assert set(r.keys()) >= {"casos", "prazos", "financeiro", "degradado"}
    assert "contadores" not in r and "decisoes" not in r
