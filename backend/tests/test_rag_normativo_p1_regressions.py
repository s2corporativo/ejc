from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest

from app.routers.rag_governance import AuthorityLevel
from app.services.ai import reranker


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _Rows(self._rows)


class _Session:
    def __init__(self, rows):
        self._db = _DB(rows)

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _metadata(status: str):
    return [
        (
            "lei-1",
            {"authority_level": "oficial_normativa", "legal_status": status},
            True,
            None,
            None,
        )
    ]


@pytest.mark.asyncio
async def test_kill_switch_desligado_preserva_norma_com_vigencia_nao_verificada(monkeypatch):
    monkeypatch.setattr(
        reranker,
        "settings",
        SimpleNamespace(RAG_EXIGIR_VIGENCIA_VERIFICADA=False),
    )
    monkeypatch.setattr(
        reranker,
        "AsyncSessionLocal",
        lambda: _Session(_metadata("vigencia_nao_verificada")),
    )

    resultado = await reranker._hidratar_governanca(
        [{"doc_id": "lei-1", "categoria": "legislacao"}]
    )

    assert [item["doc_id"] for item in resultado] == ["lei-1"]
    assert resultado[0]["situacao_juridica"]["code"] == "vigencia_nao_verificada"


@pytest.mark.asyncio
async def test_kill_switch_ligado_bloqueia_norma_com_vigencia_nao_verificada(monkeypatch):
    monkeypatch.setattr(
        reranker,
        "settings",
        SimpleNamespace(RAG_EXIGIR_VIGENCIA_VERIFICADA=True),
    )
    monkeypatch.setattr(
        reranker,
        "AsyncSessionLocal",
        lambda: _Session(_metadata("vigencia_nao_verificada")),
    )

    resultado = await reranker._hidratar_governanca(
        [{"doc_id": "lei-1", "categoria": "legislacao"}]
    )

    assert resultado == []


@pytest.mark.asyncio
async def test_revogada_permanece_bloqueada_mesmo_no_modo_de_recuperacao(monkeypatch):
    monkeypatch.setattr(
        reranker,
        "settings",
        SimpleNamespace(RAG_EXIGIR_VIGENCIA_VERIFICADA=False),
    )
    monkeypatch.setattr(
        reranker,
        "AsyncSessionLocal",
        lambda: _Session(_metadata("revogada")),
    )

    resultado = await reranker._hidratar_governanca(
        [{"doc_id": "lei-1", "categoria": "legislacao"}]
    )

    assert resultado == []


def test_proposicao_legislativa_existe_no_contrato_backend_e_frontend():
    assert "proposicao_legislativa" in get_args(AuthorityLevel)

    frontend = (
        Path(__file__).parents[2]
        / "frontend"
        / "src"
        / "components"
        / "KnowledgeGovernancePanel.tsx"
    ).read_text(encoding="utf-8")
    assert '["proposicao_legislativa", "Proposição legislativa"]' in frontend
