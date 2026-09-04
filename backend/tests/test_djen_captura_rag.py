"""DJEN → RAG por caso (I4 da análise E2E de IA 2026-09-03).

A captura por advogado (`djen_service._capturar_configurado`) passa a ingerir
a intimação de processo VINCULADO a caso ativo como `comunicacao_processual`
restrita ao cliente/caso, `rag_status='pendente'`, com a MESMA chave_origem
do ingestor por OAB (`ingestors/djen.py`) — idempotente entre os dois
caminhos. Sem caso vinculado, nada vai ao RAG (PII de terceiros).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services import djen_service, ingestion_service
from app.services.ingestors.djen import chave_origem


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DB:
    def begin_nested(self):
        return _Nested()


_ITEM = {
    "id": "abc123",
    "siglaTribunal": "TJMG",
    "tipoComunicacao": "Intimação",
    "nomeOrgao": "2ª Vara Cível de Betim",
    "dataDisponibilizacao": "2026-09-03",
    "numeroProcesso": "5001234-56.2026.8.13.0027",
    "texto": "<p>Intime-se a parte autora para manifestar sobre a contestação no prazo de 15 dias.</p>",
}
_CASO = SimpleNamespace(id="caso-A", client_id="cli-1")


@pytest.fixture
def _upsert(monkeypatch):
    chamadas: list[dict] = []

    async def fake_upsert(db, **kw):
        chamadas.append(kw)
        return "novo"

    monkeypatch.setattr(ingestion_service, "upsert_documento", fake_upsert)
    monkeypatch.setattr(get_settings(), "DJEN_CAPTURA_INGERIR_RAG", True)
    return chamadas


async def test_intimacao_vinculada_e_ingerida_restrita_ao_caso(_upsert):
    res = await djen_service._ingerir_rag_do_caso(_DB(), _ITEM, _CASO)
    assert res == "novo"
    assert len(_upsert) == 1
    kw = _upsert[0]
    assert kw["categoria"] == "comunicacao_processual"
    assert kw["client_id"] == "cli-1" and kw["case_id"] == "caso-A"
    assert kw["extra"]["rag_status"] == "pendente"
    assert kw["extra"]["tipo_fonte"] == "comunicacao_processual_oficial"
    assert kw["extra"]["origem_captura"] == "djen_service"
    assert kw["embutir_vetores"] is False       # vetoriza depois (job de órfãos)
    assert "Intime-se a parte autora" in kw["conteudo"]
    assert "<p>" not in kw["conteudo"]           # HTML limpo
    # Mesma chave do ingestor por OAB → dedup entre os dois caminhos.
    assert kw["chave_origem"] == chave_origem(_ITEM) == "djen:abc123"


async def test_flag_desligada_nao_ingere(monkeypatch, _upsert):
    monkeypatch.setattr(get_settings(), "DJEN_CAPTURA_INGERIR_RAG", False)
    assert await djen_service._ingerir_rag_do_caso(_DB(), _ITEM, _CASO) is None
    assert _upsert == []


async def test_item_sem_texto_nao_ingere(_upsert):
    assert await djen_service._ingerir_rag_do_caso(_DB(), {**_ITEM, "texto": ""}, _CASO) is None
    assert _upsert == []


async def test_falha_no_upsert_nao_derruba_a_captura(monkeypatch):
    async def explode(db, **kw):
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(ingestion_service, "upsert_documento", explode)
    monkeypatch.setattr(get_settings(), "DJEN_CAPTURA_INGERIR_RAG", True)
    assert await djen_service._ingerir_rag_do_caso(_DB(), _ITEM, _CASO) is None


def test_captura_chama_ingestao_so_com_caso_vinculado():
    """Wiring em _capturar_configurado: a ingestão RAG fica dentro do `if caso:`
    (sem caso ativo, a comunicação — PII de terceiros — não vai ao RAG)."""
    from pathlib import Path
    src = Path(djen_service.__file__).read_text(encoding="utf-8")
    inicio = src.index("async def _capturar_configurado(")
    corpo = src[inicio:]
    i_if = corpo.index("        if caso:\n")
    i_call = corpo.index("await _ingerir_rag_do_caso(db, item, caso)")
    assert i_if < i_call
    # A chamada está no bloco imediatamente após o `if caso:` (indentação de 12).
    linha = corpo[:i_call].rsplit("\n", 1)[-1]
    assert linha == "            "
