"""Regressões da governança normativa e fila de vigência (#1465/#1307)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.rag import BaseRag
from app.services.knowledge_governance import inferir_autoridade
from app.services.rag_vigencia_queue import (
    eh_pendencia_vigencia,
    listar_pendencias_vigencia,
    vigencia_normativa_confirmada,
)


class _Scalars:
    def __init__(self, docs):
        self._docs = docs

    def all(self):
        return self._docs


class _Resultado:
    def __init__(self, docs):
        self._docs = docs

    def scalars(self):
        return _Scalars(self._docs)


class _DB:
    def __init__(self, docs):
        self.docs = docs
        self.execute_calls = 0

    async def execute(self, _stmt):
        self.execute_calls += 1
        return _Resultado(self.docs)


def _doc(
    doc_id: str,
    *,
    categoria: str = "legislacao",
    base_rag=BaseRag.publica,
    client_id=None,
    case_id=None,
    vigente: bool = True,
    deleted_at=None,
    extra=None,
):
    return SimpleNamespace(
        id=doc_id,
        titulo=f"Documento {doc_id}",
        categoria=categoria,
        fonte="https://www.planalto.gov.br/ccivil_03/leis/exemplo.htm",
        tribunal=None,
        chave_origem=f"planalto:{doc_id}",
        versao=1,
        base_rag=base_rag,
        client_id=client_id,
        case_id=case_id,
        vigente=vigente,
        deleted_at=deleted_at,
        extra=dict(extra or {}),
        atualizado_em=datetime(2026, 9, 12, tzinfo=timezone.utc),
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def test_proposicao_oficial_nao_recebe_autoridade_de_norma_vigente():
    autoridade = inferir_autoridade(
        "proposicao_legislativa",
        "https://www.camara.leg.br/propostas-legislativas/123",
        {"source_official": True},
    )

    assert autoridade["code"] == "proposicao_legislativa"
    assert autoridade["code"] != "oficial_normativa"
    assert autoridade["weight"] < 100


def test_vigencia_confirmada_exige_status_origem_data_e_ausencia_de_inferencia():
    base = {
        "legal_status": "vigente",
        "legal_status_origem": "curadoria:usuario",
        "legal_status_verificado_em": "2026-09-12T10:00:00+00:00",
    }
    assert vigencia_normativa_confirmada(base) is True
    assert vigencia_normativa_confirmada({**base, "legal_status_origem": ""}) is False
    assert vigencia_normativa_confirmada({**base, "legal_status_verificado_em": ""}) is False
    assert vigencia_normativa_confirmada(
        {**base, "legal_status_inferido_em": "2026-09-12T09:00:00+00:00"}
    ) is False
    assert vigencia_normativa_confirmada(
        {
            "legal_status": "vigencia_nao_verificada",
            "legal_status_origem": "planalto:texto_compilado",
        }
    ) is False


def test_pendencia_rejeita_privado_historico_proposicao_e_ja_verificado():
    confirmado = {
        "legal_status": "vigente",
        "legal_status_origem": "curadoria:usuario",
        "legal_status_verificado_em": "2026-09-12T10:00:00+00:00",
    }
    assert eh_pendencia_vigencia(_doc("pendente")) is True
    assert eh_pendencia_vigencia(_doc("cliente", client_id="cli-1")) is False
    assert eh_pendencia_vigencia(_doc("caso", case_id="case-1")) is False
    assert eh_pendencia_vigencia(
        _doc("privado", base_rag=BaseRag.escritorio)
    ) is False
    assert eh_pendencia_vigencia(_doc("historico", vigente=False)) is False
    assert eh_pendencia_vigencia(
        _doc("projeto", categoria="proposicao_legislativa")
    ) is False
    assert eh_pendencia_vigencia(_doc("ok", extra=confirmado)) is False


@pytest.mark.asyncio
async def test_fila_e_read_only_minima_e_nao_expoe_conteudo_ou_fonte():
    docs = [
        _doc(
            "inferido",
            extra={
                "legal_status": "vigencia_nao_verificada",
                "legal_status_origem": "planalto:texto_compilado",
                "legal_status_inferido_em": "2026-09-12T09:00:00+00:00",
            },
        ),
        _doc("sem-metadado"),
        _doc("cliente", client_id="cli-1"),
        _doc("projeto", categoria="proposicao_legislativa"),
    ]
    db = _DB(docs)

    resposta = await listar_pendencias_vigencia(db, page=1, page_size=50)

    assert db.execute_calls == 1
    assert resposta["total"] == 2
    assert {item["id"] for item in resposta["data"]} == {
        "inferido",
        "sem-metadado",
    }
    for item in resposta["data"]:
        assert "conteudo" not in item
        assert "extra" not in item
        assert "fonte" not in item
        assert "client_id" not in item
        assert "case_id" not in item


@pytest.mark.asyncio
async def test_fila_paginação_e_deterministica():
    db = _DB([_doc("a"), _doc("b"), _doc("c")])

    resposta = await listar_pendencias_vigencia(db, page=2, page_size=2)

    assert resposta["total"] == 3
    assert resposta["page"] == 2
    assert resposta["page_size"] == 2
    assert [item["id"] for item in resposta["data"]] == ["c"]
