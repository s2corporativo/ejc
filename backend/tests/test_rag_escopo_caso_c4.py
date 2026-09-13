"""C4 + B7 (análise E2E de IA 2026-09-03).

C4 — isolamento por caso: `scope_case_id` é propagado onde o `case_id` já é
conhecido (deep_research, dossiê, ai_service) e a consulta ao RAG carrega o
contrato único `_FILTRO_ESCOPO_RAG` — ownership de OUTRO caso/cliente não
volta. Sem caso no escopo, `scope_client_id` sozinho mantém documentos de caso
fail-closed e gera `logger.debug`.

B7 — deep_research grava tokens/custo somando as DUAS chamadas ao gateway e
passa `entidades` do caso quando há `case_id`.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import ai_service
from app.services import deep_research_service as dr
from app.services import dossie_service


# ── ai_service: SQL da recuperação carrega o filtro por caso ─────────────────

class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeDB:
    """Captura (sql, params) de toda consulta; devolve vazio."""

    def __init__(self):
        self.consultas: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        self.consultas.append((str(stmt), dict(params or {})))
        return _Rows([])


@pytest.fixture
def _sem_embeddings(monkeypatch):
    """Força o caminho textual (sem pgvector nem modelo) e desliga reranker/FTS."""
    from app.services import embedding_service
    from app.services.ai import reranker
    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)
    monkeypatch.setattr(reranker, "disponivel", lambda: False)


async def test_busca_com_scope_case_id_aplica_filtro_por_caso(_sem_embeddings):
    db = _FakeDB()
    await ai_service.buscar_contexto_rag(
        db, "intimação prazo contestação", limite=5,
        scope_client_id="cli-1", scope_case_id="caso-A",
    )
    assert db.consultas, "a busca textual deve consultar o banco"
    sqls = [s for s, _ in db.consultas]
    params = [p for _, p in db.consultas]
    assert any("kd.client_id = NULLIF(:scope_cli, '')" in s for s in sqls)
    assert any("kd.case_id IS NULL OR kd.case_id = NULLIF(:scope_case, '')" in s
               for s in sqls)
    assert any(p.get("scope_cli") == "cli-1" for p in params)
    assert any(p.get("scope_case") == "caso-A" for p in params)
    assert any(p.get("restr_cats") == ai_service._RESTRICTED_CATS for p in params)


async def test_busca_sem_scope_case_id_nao_filtra_por_caso(_sem_embeddings):
    db = _FakeDB()
    await ai_service.buscar_contexto_rag(db, "intimação", limite=5, scope_client_id="cli-1")
    assert any("kd.case_id IS NULL OR kd.case_id = NULLIF(:scope_case, '')" in s
               for s, _ in db.consultas)
    assert any(p.get("scope_case") == "" for _, p in db.consultas)


async def test_scope_client_sem_scope_case_gera_debug(_sem_embeddings, caplog):
    db = _FakeDB()
    with caplog.at_level(logging.DEBUG, logger=ai_service.logger.name):
        await ai_service.buscar_contexto_rag(db, "x", limite=3, scope_client_id="cli-1")
    assert any("escopo de cliente sem caso" in r.getMessage() for r in caplog.records)


def test_semantica_do_filtro_por_caso():
    """O contrato novo é ownership/base, não lista de categorias por caso."""
    assert not hasattr(ai_service, "_CASE_SCOPED_CATS")
    filtro = ai_service._FILTRO_ESCOPO_RAG
    assert "base_rag" in filtro
    assert "kd.client_id = NULLIF(:scope_cli, '')" in filtro
    assert "kd.case_id IS NULL OR kd.case_id = NULLIF(:scope_case, '')" in filtro
    params = ai_service._params_escopo_rag("cli-1", "caso-A")
    assert params["scope_cli"] == "cli-1"
    assert params["scope_case"] == "caso-A"
    assert params["restr_cats"] == ai_service._RESTRICTED_CATS


# ── call sites propagam scope_case_id ────────────────────────────────────────

def _captura_rag(monkeypatch, alvo_mod, attr="buscar_contexto_rag"):
    chamadas: list[dict] = []

    async def fake(db, consulta, **kw):
        chamadas.append({"consulta": consulta, **kw})
        return []

    monkeypatch.setattr(alvo_mod, attr, fake)
    return chamadas


class _DBDR:
    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def _resp(texto, ti, to, provedor="groq", modelo="llama-3.3-70b-versatile"):
    return SimpleNamespace(texto=texto, modelo=modelo, provedor=provedor,
                           input_tokens=ti, output_tokens=to)


async def test_deep_research_propaga_scope_case_id_entidades_e_custo(monkeypatch):
    rag = _captura_rag(monkeypatch, dr)
    chats: list[dict] = []

    async def fake_chat(*a, **kw):
        chats.append(kw)
        if len(chats) == 1:
            return _resp("Cabimento da tese principal\nProvas necessárias", 100, 20)
        return _resp("Síntese final da pesquisa", 1000, 300)

    async def fake_precedentes(termo, fontes=None, numero_cnj=None, por_pagina=8):
        return {"fontes": {}, "precedentes": []}

    async def fake_entidades(db, case_id):
        return {"cliente": ["Fulano de Tal"]}

    monkeypatch.setattr(dr, "gw_chat", fake_chat)
    monkeypatch.setattr(dr, "buscar_precedentes", fake_precedentes)
    monkeypatch.setattr(dr, "entidades_do_caso", fake_entidades)
    monkeypatch.setattr(ai_service.settings, "GROQ_PRECO_INPUT_BRL_POR_MILHAO", 1.0, raising=False)
    monkeypatch.setattr(ai_service.settings, "GROQ_PRECO_OUTPUT_BRL_POR_MILHAO", 2.0, raising=False)

    db = _DBDR()
    entrada = dr.DeepResearchInput(
        tese="dano moral", fatos="fatos", area="consumidor",
        case_id="caso-A", scope_client_id="cli-1",
    )
    out = await dr.executar_deep_research(db, entrada, user_id="u1")

    # C4: toda consulta ao RAG leva cliente E caso.
    assert rag and all(c["scope_client_id"] == "cli-1" for c in rag)
    assert all(c["scope_case_id"] == "caso-A" for c in rag)
    # entidades do caso vão às DUAS chamadas do gateway.
    assert len(chats) == 2
    assert all(c.get("entidades") == {"cliente": ["Fulano de Tal"]} for c in chats)
    # B7: tokens/custo somados das duas chamadas.
    log = db.added[0]
    assert log.tokens_input == 1100
    assert log.tokens_output == 320
    esperado = (Decimal(1100) / Decimal(1_000_000)) * Decimal("1.0") + \
               (Decimal(320) / Decimal(1_000_000)) * Decimal("2.0")
    assert log.custo_estimado == esperado.quantize(Decimal("0.000001"))
    assert out["ai_log_id"] == log.id


async def test_deep_research_sem_case_id_nao_busca_entidades(monkeypatch):
    _captura_rag(monkeypatch, dr)

    async def fake_chat(*a, **kw):
        return _resp("Resultado", None, None)

    async def fake_precedentes(termo, fontes=None, numero_cnj=None, por_pagina=8):
        return {"fontes": {}, "precedentes": []}

    async def explode(db, case_id):
        raise AssertionError("entidades_do_caso não deve ser chamado sem case_id")

    monkeypatch.setattr(dr, "gw_chat", fake_chat)
    monkeypatch.setattr(dr, "buscar_precedentes", fake_precedentes)
    monkeypatch.setattr(dr, "entidades_do_caso", explode)

    db = _DBDR()
    await dr.executar_deep_research(
        db, dr.DeepResearchInput(tese="t", fatos="f"), user_id="u1"
    )
    log = db.added[0]
    # Sem tokens informados pelo provedor: não inventa zero.
    assert log.tokens_input is None and log.tokens_output is None
    assert log.custo_estimado is None


async def test_dossie_propaga_scope_case_id(monkeypatch):
    rag = _captura_rag(monkeypatch, ai_service)
    dados = {"caso": {"area": "civil", "titulo": "Cobrança", "descricao": "x",
                      "client_id": "cli-1", "case_id": "caso-A"}}
    await dossie_service._jurisprudencia_relacionada(object(), dados)
    assert rag[0]["scope_client_id"] == "cli-1"
    assert rag[0]["scope_case_id"] == "caso-A"


async def test_dados_caso_expoe_case_id_para_o_escopo():
    class _Res:
        def __init__(self, obj):
            self._obj = obj

        def scalar_one_or_none(self):
            return self._obj

    class _DB:
        async def execute(self, stmt):
            return _Res(SimpleNamespace(
                id="caso-A", numero_interno="DPT-1", titulo="T", status="aberto",
                area="civil", descricao_fatos="d", created_at=None, client_id="cli-1",
            ))

    dados = await dossie_service._dados_caso(_DB(), "caso-A")
    assert dados["case_id"] == "caso-A" and dados["client_id"] == "cli-1"


async def test_detectar_teses_ocultas_propaga_scope_case_id(monkeypatch):
    rag = _captura_rag(monkeypatch, ai_service)

    async def fake_entidades(db, case_id):
        return {}

    async def fake_gateway(*a, **kw):
        raise RuntimeError("gateway desligado no teste")

    async def fake_sigilo(db, case_id):
        return None

    import app.services.ai.entidades_caso as ec
    monkeypatch.setattr(ec, "entidades_do_caso", fake_entidades)
    monkeypatch.setattr(ai_service, "_gateway_text", fake_gateway)
    monkeypatch.setattr(ai_service, "_modo_sigilo_caso", fake_sigilo)

    await ai_service.detectar_teses_ocultas(
        object(), "u1", "fatos do caso sem PII", "civil",
        case_id="caso-A", scope_client_id="cli-1",
    )
    assert rag and rag[0]["scope_client_id"] == "cli-1"
    assert rag[0]["scope_case_id"] == "caso-A"
