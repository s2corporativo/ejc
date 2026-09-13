from __future__ import annotations

import pytest

from app.services.ai import reranker
from app.services.citation_check import _fonte_artigo
from app.services.knowledge_governance import inferir_autoridade


class _FalhaGovernanca:
    async def __aenter__(self):
        raise RuntimeError("governanca_indisponivel")

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ResultadoVazio:
    def first(self):
        return None


class _DBCapturaSQL:
    def __init__(self) -> None:
        self.sql = ""

    async def execute(self, stmt, params):
        self.sql = str(stmt)
        return _ResultadoVazio()


def test_categoria_normativa_reconhece_categoria_e_autoridade() -> None:
    assert reranker._categoria_normativa({"categoria": "legislacao"}) is True
    assert (
        reranker._categoria_normativa(
            {"categoria": "referencial", "extra": {"authority_level": "oficial_normativa"}}
        )
        is True
    )
    assert reranker._categoria_normativa({"categoria": "jurisprudencia"}) is False


@pytest.mark.asyncio
async def test_governanca_indisponivel_remove_candidatos_normativos(monkeypatch) -> None:
    monkeypatch.setattr(reranker, "AsyncSessionLocal", lambda: _FalhaGovernanca())
    candidatos = [
        {"doc_id": "lei-1", "categoria": "legislacao"},
        {"doc_id": "juris-1", "categoria": "jurisprudencia"},
        {
            "doc_id": "norma-2",
            "categoria": "referencial",
            "extra": {"authority_level": "oficial_normativa"},
        },
    ]

    resultado = await reranker._hidratar_governanca(candidatos)

    assert [item["doc_id"] for item in resultado] == ["juris-1"]


@pytest.mark.asyncio
async def test_citacao_de_direito_atual_exclui_status_bloqueados() -> None:
    db = _DBCapturaSQL()

    await _fonte_artigo(db, "300", "cpc", vigente=True)

    sql = db.sql.lower()
    assert "legal_status" in sql
    assert "revogada" in sql
    assert "suspensa" in sql
    assert "not in" in sql


def test_proposicao_legislativa_nao_recebe_autoridade_normativa() -> None:
    proposicao = inferir_autoridade(
        "proposicao_legislativa",
        "https://www.senado.leg.br/atividade/materia",
    )
    norma = inferir_autoridade(
        "legislacao",
        "https://www.planalto.gov.br/ccivil_03/leis/l0000.htm",
    )
    proposicao_nao_oficial = inferir_autoridade(
        "proposicao_legislativa",
        "https://example.org/projeto",
    )

    assert proposicao["code"] == "proposicao_legislativa"
    assert proposicao["official"] is True
    assert proposicao["weight"] < norma["weight"]
    assert norma["code"] == "oficial_normativa"
    assert proposicao_nao_oficial["code"] == "referencial"
    assert proposicao_nao_oficial["official"] is False
