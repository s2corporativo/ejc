"""C5 (análise E2E de IA 2026-09-03) — chunk coerente com a janela do modelo.

Invariantes:
  • `legal_chunker._MAX_DEFAULT` e `ingestion_service.CHUNK_TAMANHO` nunca
    excedem `EMBEDDINGS_MAX_CHARS` (cauda acima da janela ficaria sem vetor);
  • legislação vira chunks por artigo, nenhum acima do teto;
  • `chunks_para_ingestao` só atua nas categorias jurídicas (fallback = None);
  • `hash_conteudo` do upsert é do documento inteiro — independe dos chunks.
"""
from __future__ import annotations

import re

import pytest

from app.core.config import get_settings
from app.services import ingestion_service, legal_chunker
from app.services.legal_chunker import chunk_documento_juridico, chunks_para_ingestao


def test_teto_default_do_chunker_nao_excede_janela_do_modelo():
    teto = get_settings().EMBEDDINGS_MAX_CHARS
    assert legal_chunker._MAX_DEFAULT <= teto, (
        f"legal_chunker._MAX_DEFAULT={legal_chunker._MAX_DEFAULT} > "
        f"EMBEDDINGS_MAX_CHARS={teto}: a cauda do chunk ficaria sem vetor"
    )


def test_chunk_tamanho_da_ingestao_nao_excede_janela_do_modelo():
    teto = get_settings().EMBEDDINGS_MAX_CHARS
    assert ingestion_service.CHUNK_TAMANHO <= teto


def _lei_com_artigos(n: int, tamanho_art: int = 600) -> str:
    partes = ["LEI Nº 9.999, DE 1º DE JANEIRO DE 2026. Dispõe sobre o teste."]
    for i in range(1, n + 1):
        corpo = (f"Art. {i}º Esta é a redação do artigo {i}. "
                 + ("Parágrafo único. Regra complementar do artigo. " * (tamanho_art // 46)))
        partes.append(corpo.strip())
    return "\n\n".join(partes)


def test_legislacao_vira_chunks_por_artigo_dentro_do_teto():
    texto = _lei_com_artigos(8)
    chunks = chunks_para_ingestao(texto, "legislacao_geral")
    assert chunks and len(chunks) >= 8
    teto = get_settings().EMBEDDINGS_MAX_CHARS
    assert all(len(c) <= teto for c in chunks)
    # Cada artigo abre o próprio chunk (fronteira semântica, não por tamanho).
    inicios = [c for c in chunks if re.match(r"^Art\. \d+º", c)]
    assert len(inicios) == 8


def test_pedido_acima_do_teto_e_rebaixado_para_a_janela():
    teto = get_settings().EMBEDDINGS_MAX_CHARS
    texto = "Fundamento jurídico completo e detalhado. " * 400   # ~17k chars
    chunks = chunk_documento_juridico(texto, categoria="doutrina", max_chars=teto * 3)
    assert len(chunks) > 1
    assert all(len(c) <= teto for c in chunks)


def test_heading_repetido_nao_estoura_o_teto_nem_some():
    texto = "## RATIO DECIDENDI DO ACÓRDÃO\n\n" + ("Fundamento jurídico completo. " * 150)
    chunks = chunk_documento_juridico(texto, categoria="jurisprudencia_stj", max_chars=900)
    assert len(chunks) > 1
    assert all(len(c) <= 900 for c in chunks)
    assert all(c.startswith("## RATIO DECIDENDI") for c in chunks)


@pytest.mark.parametrize("categoria", [
    "legislacao_geral", "legislacao_trabalhista", "sumula_stj", "sumula_tjmg",
    "jurisprudencia_tjmg", "jurisprudencia", "doutrina",
])
def test_categorias_juridicas_usam_o_chunker(categoria):
    assert legal_chunker.categoria_usa_chunker_juridico(categoria)
    assert chunks_para_ingestao(_lei_com_artigos(2), categoria)


@pytest.mark.parametrize("categoria", [
    "comunicacao_processual", "peca_interna", "precedente_interno",
    "modelo_documento_juridico", "outros", "", None,
])
def test_demais_categorias_caem_no_corte_por_tamanho(categoria):
    assert not legal_chunker.categoria_usa_chunker_juridico(categoria)
    assert chunks_para_ingestao(_lei_com_artigos(2), categoria) is None


def test_texto_vazio_nao_gera_chunks_e_cai_no_fallback():
    assert chunks_para_ingestao("   ", "legislacao_geral") is None


# ── hash_conteudo independe da estratégia de chunking ────────────────────────

class _Res:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self):
        self.added = []

    async def execute(self, stmt, params=None):
        return _Res([])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


async def test_hash_conteudo_e_do_documento_inteiro_nao_dos_chunks(monkeypatch):
    from app.models.rag import KnowledgeChunk, KnowledgeDoc

    async def sem_vetores(textos, *a, **k):
        return None

    monkeypatch.setattr(ingestion_service, "gerar_embeddings", sem_vetores)
    texto = _lei_com_artigos(4)

    db1, db2 = _FakeDB(), _FakeDB()
    await ingestion_service.upsert_documento(
        db1, titulo="Lei", categoria="legislacao_geral", conteudo=texto,
        chave_origem="lei:teste", chunks=chunks_para_ingestao(texto, "legislacao_geral"),
    )
    await ingestion_service.upsert_documento(
        db2, titulo="Lei", categoria="legislacao_geral", conteudo=texto,
        chave_origem="lei:teste",   # sem chunks → corte por tamanho
    )
    doc1 = next(o for o in db1.added if isinstance(o, KnowledgeDoc))
    doc2 = next(o for o in db2.added if isinstance(o, KnowledgeDoc))
    assert doc1.hash_conteudo == doc2.hash_conteudo
    n1 = sum(isinstance(o, KnowledgeChunk) for o in db1.added)
    n2 = sum(isinstance(o, KnowledgeChunk) for o in db2.added)
    assert n1 >= 4 and n2 >= 1   # estratégias diferentes, mesmo hash
