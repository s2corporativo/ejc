"""Fase 1 RAG — chunker unificado + gate de confiança na ingestão.

1) O router /rag usa o MESMO chunker do ingestion_service (heurística de
   fronteira de frase) — sem duplicata divergente.
2) Ingestão manual carrega `confianca` (vocabulário canônico da governança:
   alta|media|baixa|bloqueado), persistida em extra["confidence_level"].
3) A busca RAG expõe `confianca` nos resultados (COALESCE com default media).
"""
import inspect

import pytest
from pydantic import ValidationError


# ── 1. Chunker unificado ──────────────────────────────────────────────────────

def test_router_usa_chunker_do_ingestion_service():
    import app.routers.rag as rag_router
    from app.services.ingestion_service import chunk_texto
    # O chunker duplicado (_chunk_texto) foi removido do router.
    assert not hasattr(rag_router, "_chunk_texto")
    assert rag_router.chunk_texto is chunk_texto


def test_chunk_texto_corta_em_fronteira_de_frase():
    from app.services.ingestion_service import chunk_texto
    frase = "Esta é uma sentença jurídica de teste com conteúdo relevante. "
    texto = frase * 60  # >> 1200 chars
    chunks = chunk_texto(texto)
    assert len(chunks) > 1
    # heurística: chunks intermediários terminam em fronteira natural (.)
    assert chunks[0].rstrip().endswith(".")
    # nada se perde além do overlap: todo chunk é substring do texto normalizado
    from app.services.ingestion_service import normalizar
    norm = normalizar(texto)
    assert all(c in norm for c in chunks)


def test_chunk_texto_vazio_e_curto():
    from app.services.ingestion_service import chunk_texto
    assert chunk_texto("") == []
    assert chunk_texto("texto curto") == ["texto curto"]


# ── 2. Gate de confiança na ingestão manual ───────────────────────────────────

def test_ingest_request_tem_confianca_default_media():
    from app.routers.rag import IngestRequest
    req = IngestRequest(titulo="t", categoria="legislacao", conteudo="x" * 60)
    assert req.confianca == "media"


def test_ingest_request_valida_vocabulario_da_governanca():
    from app.routers.rag import IngestRequest
    for v in ("alta", "media", "baixa", "bloqueado"):
        assert IngestRequest(titulo="t", categoria="legislacao",
                             conteudo="x" * 60, confianca=v).confianca == v
    with pytest.raises(ValidationError):
        IngestRequest(titulo="t", categoria="legislacao",
                      conteudo="x" * 60, confianca="altissima")


def test_vocabulario_e_o_mesmo_literal_da_governanca():
    # rag.py reutiliza o Literal Confianca de ia_governanca (não inventa outro).
    import typing
    from app.routers.rag import Confianca as C1
    from app.routers.ia_governanca import Confianca as C2
    assert C1 is C2
    assert set(typing.get_args(C1)) == {"alta", "media", "baixa", "bloqueado"}


def test_upsert_documento_aceita_confianca():
    from app.services.ingestion_service import upsert_documento
    assert "confianca" in inspect.signature(upsert_documento).parameters


class _ResUpsert:
    def scalar_one_or_none(self):
        return None


class _FakeDBUpsert:
    """Fake mínimo: nenhum doc vigente existente; captura objetos adicionados."""
    def __init__(self):
        self.added = []

    async def execute(self, sql, params=None):
        return _ResUpsert()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


async def test_upsert_documento_persiste_confianca_no_extra():
    from app.models.rag import KnowledgeDoc
    from app.services.ingestion_service import upsert_documento

    db = _FakeDBUpsert()
    res = await upsert_documento(
        db, titulo="Lei X", categoria="legislacao",
        conteudo="Conteúdo jurídico de teste suficientemente longo para ingestão.",
        chave_origem="teste:lei-x", extra={"origem": "teste"}, confianca="alta",
        embutir_vetores=False,
    )
    assert res == "novo"
    docs = [o for o in db.added if isinstance(o, KnowledgeDoc)]
    assert len(docs) == 1
    # chave canônica lida por ia_governanca._conf; extra original preservado
    assert docs[0].extra["confidence_level"] == "alta"
    assert docs[0].extra["origem"] == "teste"


async def test_upsert_documento_sem_confianca_nao_polui_extra():
    from app.models.rag import KnowledgeDoc
    from app.services.ingestion_service import upsert_documento

    db = _FakeDBUpsert()
    await upsert_documento(
        db, titulo="Lei Y", categoria="legislacao",
        conteudo="Outro conteúdo jurídico de teste suficientemente longo aqui.",
        chave_origem="teste:lei-y", embutir_vetores=False,
    )
    doc = [o for o in db.added if isinstance(o, KnowledgeDoc)][0]
    # default None → não grava chave; a busca assume "media" via COALESCE
    assert doc.extra is None


# ── 3. Busca expõe confiança ──────────────────────────────────────────────────

class _CaptureDB:
    def __init__(self):
        self.sql = ""
        self.params = {}

    async def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params or {}
        return []


async def test_busca_textual_seleciona_confianca():
    from app.services.ai_service import buscar_contexto_rag
    db = _CaptureDB()
    await buscar_contexto_rag(db, "consulta qualquer de teste", limite=3)
    assert "confidence_level" in db.sql
    assert "AS confianca" in db.sql
    # default do vocabulário quando o doc não passou pela curadoria
    assert "'media'" in db.sql


def test_sql_confianca_usa_vocabulario_com_fallback():
    from app.services.ai_service import _SQL_CONFIANCA
    assert "confidence_level" in _SQL_CONFIANCA
    assert "confianca" in _SQL_CONFIANCA          # chave legada
    assert "'media'" in _SQL_CONFIANCA            # default


def test_endpoint_buscar_delega_ao_pipeline_governado():
    # A rota não pode manter SQL vetorial próprio: isso já criou bypass de
    # aprovação, quarentena de súmulas e exclusão do corpus fictício.
    import inspect as _i
    from app.routers.rag import buscar
    src = _i.getsource(buscar)
    assert "buscar_contexto_rag" in src
    assert "<=>" not in src
    assert '"pipeline": "hibrida_governada"' in src


def test_chave_manual_e_estavel_por_origem_e_isolada_por_usuario():
    from app.routers.rag import _chave_ingestao_manual
    kw = {"titulo": "Lei de teste", "categoria": "legislacao",
          "fonte": "https://example.test/lei", "tribunal": None}
    k1 = _chave_ingestao_manual(actor_id="u1", **kw)
    k2 = _chave_ingestao_manual(actor_id="u1", **kw)
    k3 = _chave_ingestao_manual(actor_id="u2", **kw)
    assert k1 == k2
    assert k1 != k3
    assert "example.test" not in k1
