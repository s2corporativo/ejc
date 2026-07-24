from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import rag_traceable


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _FakeDB:
    def __init__(self, rows=None, error: Exception | None = None):
        self.rows = rows or []
        self.error = error
        self.calls = 0

    async def execute(self, _query):
        self.calls += 1
        if self.error:
            raise self.error
        return _Result(self.rows)


def _doc(doc_id="doc-1"):
    return SimpleNamespace(
        id=doc_id,
        titulo="Contestação modelo",
        categoria="precedente_interno",
        fonte="contestacao.pdf",
        tribunal=None,
        extra={
            "rag_status": "aprovado",
            "proveniencia": {"pagina": 4, "processo_origem": "proc-123"},
        },
        client_id="cliente-nao-expor",
        case_id="caso-1",
        chave_origem="manual:doc-1",
        hash_conteudo="abc123",
        atualizado_em=None,
        versao=2,
        vigente=True,
        revisado=True,
    )


@pytest.mark.asyncio
async def test_enriquece_lote_com_uma_unica_consulta_e_preserva_ordem():
    db = _FakeDB(rows=[_doc()])
    resultados = [
        {
            "chunk_id": "chunk-2",
            "doc_id": "doc-1",
            "conteudo": "Segundo trecho",
            "score": 0.81,
        },
        {
            "chunk_id": "chunk-1",
            "doc_id": "doc-1",
            "conteudo": "Primeiro trecho",
            "score": 0.79,
        },
    ]

    saida = await rag_traceable.enriquecer_resultados_com_proveniencia(
        db,
        resultados,
    )

    assert db.calls == 1
    assert [item["chunk_id"] for item in saida] == ["chunk-2", "chunk-1"]
    assert [item["score"] for item in saida] == [0.81, 0.79]
    assert saida[0]["proveniencia"]["status_fonte"] == "confirmada"
    assert saida[0]["proveniencia"]["pagina"] == 4
    assert saida[0]["proveniencia"]["processo_origem"] == "proc-123"
    assert "client_id" not in saida[0]["proveniencia"]


@pytest.mark.asyncio
async def test_documento_ausente_recebe_estado_fail_safe():
    db = _FakeDB(rows=[])

    saida = await rag_traceable.enriquecer_resultados_com_proveniencia(
        db,
        [
            {
                "chunk_id": "chunk-1",
                "doc_id": "doc-ausente",
                "titulo": "Fonte não recarregada",
                "conteudo": "Trecho preservado",
                "score": 0.7,
            }
        ],
    )

    assert db.calls == 1
    assert saida[0]["score"] == 0.7
    assert (
        saida[0]["proveniencia"]["status_fonte"]
        == "identificacao_insuficiente"
    )


@pytest.mark.asyncio
async def test_falha_no_enriquecimento_nao_derruba_retrieval():
    db = _FakeDB(error=RuntimeError("banco indisponível"))
    resultados = [
        {
            "chunk_id": "chunk-1",
            "doc_id": "doc-1",
            "titulo": "Documento",
            "conteudo": "Trecho",
            "score": 0.9,
        }
    ]

    saida = await rag_traceable.enriquecer_resultados_com_proveniencia(
        db,
        resultados,
    )

    assert db.calls == 1
    assert saida[0]["score"] == 0.9
    assert saida[0]["proveniencia"]["status_fonte"] in {
        "identificacao_insuficiente",
        "pendente_conferencia",
    }


@pytest.mark.asyncio
async def test_wrapper_repassa_filtros_ao_retrieval_canonico(monkeypatch):
    chamadas = []

    async def _buscar(db, consulta, **kwargs):
        chamadas.append((db, consulta, kwargs))
        return []

    monkeypatch.setattr(rag_traceable, "buscar_contexto_rag", _buscar)
    db = _FakeDB()

    saida = await rag_traceable.buscar_contexto_rag_rastreavel(
        db,
        "responsabilidade civil",
        limite=9,
        categorias=["jurisprudencia_stj"],
        modo_or=True,
        scope_client_id="cliente-1",
        incluir_historico=True,
        incluir_ficticio=False,
    )

    assert saida == []
    assert chamadas == [
        (
            db,
            "responsabilidade civil",
            {
                "limite": 9,
                "categorias": ["jurisprudencia_stj"],
                "modo_or": True,
                "scope_client_id": "cliente-1",
                "incluir_historico": True,
                "incluir_ficticio": False,
            },
        )
    ]
    assert db.calls == 0
