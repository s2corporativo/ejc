"""Regressões da auditoria ponta-a-ponta do RAG — 2026-09-19.

Cobre somente invariantes introduzidas pelo hardening:
- andamento processual é sempre categoria restrita;
- métricas usam a mesma elegibilidade estrutural do retrieval;
- HyDE respeita modo de sanitização e falha fechado quando o sigilo do caso
  não pode ser confirmado;
- perna pg_trgm usa operador indexável;
- nova versão com decisão humana volta para curadoria pendente.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.rag import KnowledgeDoc


def test_andamento_processual_e_restrito_estaticamente():
    from app.services import ai_service

    assert "andamento_processual" in ai_service._RESTRICTED_CATS


def test_elegibilidade_de_metricas_nao_depende_de_bind():
    from app.services import ai_service

    sql = ai_service.filtro_elegibilidade_rag_metricas()
    assert ":restr_cats" not in sql
    assert "base_rag" in sql
    assert "andamento_processual" in sql
    assert "kd.client_id IS NOT NULL" in sql


@pytest.mark.asyncio
async def test_hyde_propaga_modo_sanitizacao(monkeypatch):
    from app.services import ai_service
    from app.services.ai.sanitization_policy import ModoSanitizacao

    capturado = {}

    async def fake_chat(*args, **kwargs):
        capturado.update(kwargs)
        return SimpleNamespace(texto="Hipótese jurídica curta.")

    monkeypatch.setattr(ai_service, "gw_chat", fake_chat)
    monkeypatch.setattr(ai_service.settings, "RAG_HYDE_ENABLED", True)

    out = await ai_service._hyde_expandir(
        "consulta jurídica",
        modo_sanitizacao=ModoSanitizacao.LOCAL_COMPLETO,
    )

    assert "Hipótese jurídica curta." in out
    assert capturado["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO


class _Rows:
    def __iter__(self):
        return iter(())


class _DB:
    def __init__(self):
        self.sqls = []

    async def execute(self, stmt, params=None):
        self.sqls.append(str(stmt))
        return _Rows()


@pytest.mark.asyncio
async def test_hyde_falha_fechado_quando_sigilo_do_caso_nao_pode_ser_confirmado(monkeypatch):
    from app.services import ai_service, embedding_service
    from app.services.ai import reranker

    async def sigilo_indisponivel(db, case_id):
        raise RuntimeError("falha simulada")

    async def hyde_nao_pode_rodar(*args, **kwargs):
        raise AssertionError("HyDE não deve rodar sem confirmação do piso de sigilo")

    async def sem_embedding(textos, modo="passage"):
        return None

    monkeypatch.setattr(ai_service, "_modo_sigilo_caso", sigilo_indisponivel)
    monkeypatch.setattr(ai_service, "_hyde_expandir", hyde_nao_pode_rodar)
    monkeypatch.setattr(embedding_service, "disponivel", lambda: True)
    monkeypatch.setattr(embedding_service, "gerar_embeddings", sem_embedding)
    monkeypatch.setattr(reranker, "disponivel", lambda: False)

    db = _DB()
    out = await ai_service.buscar_contexto_rag(
        db,
        "consulta jurídica",
        limite=3,
        scope_client_id="cli-1",
        scope_case_id="caso-1",
    )

    assert out == []


@pytest.mark.asyncio
async def test_perna_trigram_usa_operador_indexavel(monkeypatch):
    from app.services import ai_service

    monkeypatch.setattr(ai_service.settings, "RAG_FTS_ENABLED", False)
    db = _DB()
    semantico = [{
        "chunk_id": "c1",
        "doc_id": "d1",
        "conteudo": "responsabilidade civil",
        "titulo": "Doc",
        "categoria": "jurisprudencia",
        "fonte": "teste",
        "confianca": "alta",
        "versao": 1,
        "score": 0.9,
    }]

    out = await ai_service._fundir_lexical(
        db, "responsabilidade civil", semantico, 1, None
    )

    sql = "\n".join(db.sqls)
    assert "SET LOCAL pg_trgm.similarity_threshold = 0.05" in sql
    assert "kc.conteudo % :q" in sql
    assert "similarity(kc.conteudo, :q) > 0.05" not in sql
    assert out and out[0]["chunk_id"] == "c1"


class _ExistingResult:
    def __init__(self, obj):
        self.obj = obj

    def scalar_one_or_none(self):
        return self.obj


class _UpsertDB:
    def __init__(self, existing):
        self.existing = existing
        self.added = []

    async def execute(self, stmt, params=None):
        return _ExistingResult(self.existing)

    async def flush(self):
        return None

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_nova_versao_com_decisao_humana_volta_para_pendente():
    from app.services.ingestion_service import upsert_documento

    existente = KnowledgeDoc(
        id="old",
        titulo="Documento",
        categoria="jurisprudencia",
        chave_origem="teste:doc",
        hash_conteudo="hash-antigo",
        status_indexacao="indexado",
        versao=1,
        vigente=True,
        extra={
            "rag_status": "recusado",
            "human_reviewed": True,
            "curadoria": {"notas": "revisão anterior"},
        },
    )
    db = _UpsertDB(existente)

    resultado = await upsert_documento(
        db,
        titulo="Documento",
        categoria="jurisprudencia",
        conteudo=(
            "Conteúdo jurídico novo e materialmente diferente da versão anterior, "
            "com tamanho suficiente para gerar uma nova versão controlada."
        ),
        chave_origem="teste:doc",
        extra={"rag_status": "aprovado"},
        embutir_vetores=False,
    )

    novos_docs = [x for x in db.added if isinstance(x, KnowledgeDoc)]
    assert resultado == "atualizado"
    assert len(novos_docs) == 1
    novo = novos_docs[0]
    assert novo.extra["rag_status"] == "pendente"
    assert novo.extra["requires_human_review"] is True
    assert novo.extra["human_reviewed"] is False
    assert novo.extra["previous_rag_status"] == "recusado"
    assert "curadoria" not in novo.extra


def test_dashboard_rag_usa_os_mesmos_gates_do_retrieval():
    import inspect

    from app.routers.rag import stats_conhecimento, status_indexacao_rag

    for fn in (stats_conhecimento, status_indexacao_rag):
        src = inspect.getsource(fn)
        assert "filtro_elegibilidade_rag_metricas()" in src
        assert "filtros_gate_rag()" in src
        assert "vigente = TRUE" in src
        assert "EXISTS (SELECT 1 FROM knowledge_chunks" in src
