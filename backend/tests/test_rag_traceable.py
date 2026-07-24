from __future__ import annotations

from datetime import UTC, datetime
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


def _doc(doc_id="doc-1", case_id="caso-1"):
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
        base_rag=SimpleNamespace(value="caso"),
        client_id="cliente-nao-expor",
        case_id=case_id,
        chave_origem="manual:doc-1",
        hash_conteudo="abc123",
        atualizado_em=None,
        versao=2,
        vigente=True,
        revisado=True,
        revisado_em=datetime.now(UTC),
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
        case_id_esperado="caso-1",
    )

    assert db.calls == 1
    assert [item["chunk_id"] for item in saida] == ["chunk-2", "chunk-1"]
    assert [item["score"] for item in saida] == [0.81, 0.79]
    assert saida[0]["proveniencia"]["status_conferencia"] == "confirmada"
    assert saida[0]["proveniencia"]["nivel_confidencialidade"] == "confidencial"
    assert saida[0]["proveniencia"]["pagina"] == 4
    assert saida[0]["proveniencia"]["processo_origem"] == "proc-123"
    assert saida[0]["proveniencia"]["confianca_extracao"] == 0.81
    assert "client_id" not in saida[0]["proveniencia"]


@pytest.mark.asyncio
async def test_documento_ausente_recebe_estado_fail_safe_fora_de_caso():
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
        saida[0]["proveniencia"]["status_conferencia"]
        == "identificacao_insuficiente"
    )
    assert saida[0]["proveniencia"]["confianca_extracao"] == 0.7


@pytest.mark.asyncio
async def test_documento_ausente_e_removido_quando_ha_caso_esperado():
    db = _FakeDB(rows=[])

    saida = await rag_traceable.enriquecer_resultados_com_proveniencia(
        db,
        [
            {
                "chunk_id": "chunk-1",
                "doc_id": "doc-ausente",
                "titulo": "Fonte sem escopo recarregado",
                "conteudo": "Trecho que não pode permanecer sem validar o caso",
                "score": 0.7,
            }
        ],
        case_id_esperado="caso-1",
    )

    assert db.calls == 1
    assert saida == []


@pytest.mark.asyncio
async def test_resultado_sem_identificador_nao_fabrica_proveniencia():
    db = _FakeDB()

    saida = await rag_traceable.enriquecer_resultados_com_proveniencia(
        db,
        [{"conteudo": "Trecho sem origem verificável", "score": 0.5}],
    )

    assert db.calls == 0
    assert saida[0]["proveniencia"] is None
    assert saida[0]["proveniencia_erro"] == "origem sem identificação verificável"


@pytest.mark.asyncio
async def test_falha_no_enriquecimento_nao_derruba_retrieval_fora_de_caso():
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
    assert (
        saida[0]["proveniencia"]["status_conferencia"]
        == "identificacao_insuficiente"
    )


@pytest.mark.asyncio
async def test_falha_no_enriquecimento_remove_resultado_em_contexto_de_caso():
    db = _FakeDB(error=RuntimeError("banco indisponível"))

    saida = await rag_traceable.enriquecer_resultados_com_proveniencia(
        db,
        [
            {
                "chunk_id": "chunk-1",
                "doc_id": "doc-1",
                "titulo": "Documento",
                "conteudo": "Trecho",
                "score": 0.9,
            }
        ],
        case_id_esperado="caso-1",
    )

    assert db.calls == 1
    assert saida == []


@pytest.mark.asyncio
async def test_fonte_de_outro_caso_e_removida_do_resultado():
    db = _FakeDB(rows=[_doc(case_id="caso-2")])

    saida = await rag_traceable.enriquecer_resultados_com_proveniencia(
        db,
        [
            {
                "chunk_id": "chunk-1",
                "doc_id": "doc-1",
                "conteudo": "Conteúdo que não pode vazar",
                "score": 0.9,
            }
        ],
        case_id_esperado="caso-1",
    )

    assert db.calls == 1
    assert saida == []


@pytest.mark.asyncio
async def test_wrapper_repassa_filtros_e_case_id_ao_enriquecimento(monkeypatch):
    chamadas_busca = []
    chamadas_enriquecimento = []

    async def _buscar(db, consulta, **kwargs):
        chamadas_busca.append((db, consulta, kwargs))
        return [{"chunk_id": "chunk-1", "doc_id": "doc-1"}]

    async def _enriquecer(db, resultados, **kwargs):
        chamadas_enriquecimento.append((db, resultados, kwargs))
        return []

    monkeypatch.setattr(rag_traceable, "buscar_contexto_rag", _buscar)
    monkeypatch.setattr(
        rag_traceable,
        "enriquecer_resultados_com_proveniencia",
        _enriquecer,
    )
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
        case_id_esperado="caso-1",
    )

    assert saida == []
    assert chamadas_busca == [
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
    assert chamadas_enriquecimento == [
        (
            db,
            [{"chunk_id": "chunk-1", "doc_id": "doc-1"}],
            {"case_id_esperado": "caso-1"},
        )
    ]
