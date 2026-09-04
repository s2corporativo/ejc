"""Regressão do escopo RAG no encerramento de caso (#1466).

O fluxo legado de `cases.encerrar_caso` usa `chave_origem="caso:<id>"` e não
passa `client_id` diretamente. O hardening instalado no boot deve resolver o
escopo exclusivamente a partir desse identificador canônico do próprio caso e
repassar `client_id + case_id` ao `upsert_documento` real.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


class _DBFake:
    def __init__(self, case):
        self.case = case
        self.get_calls = []

    async def get(self, model, entity_id):
        self.get_calls.append((model, entity_id))
        return self.case


@pytest.mark.asyncio
async def test_precedente_caso_resolve_client_e_case_scope_antes_do_upsert(monkeypatch):
    from app.services import ai_core_hardening_patch as hardening
    from app.services import ingestion_service

    capturado = {}

    async def fake_upsert(db, **kwargs):
        del db
        capturado.update(kwargs)
        return "novo"

    case = SimpleNamespace(
        id="case-1466",
        client_id="client-1466",
        deleted_at=None,
        numero_interno="EJC-1466",
    )
    db = _DBFake(case)

    # Reconstrói apenas este adapter sobre uma função neutra para verificar o
    # contrato sem tocar banco, embeddings ou dados reais.
    monkeypatch.setattr(ingestion_service, "upsert_documento", fake_upsert)
    monkeypatch.setattr(
        ingestion_service,
        "_ejc_scope_resolver_installed",
        False,
        raising=False,
    )
    hardening._instalar_resolucao_escopo_rag()

    resultado = await ingestion_service.upsert_documento(
        db,
        titulo="Precedente interno fictício",
        categoria="precedente_interno",
        conteudo="Conteúdo fictício suficiente apenas para testar o escopo.",
        chave_origem="caso:case-1466",
        fonte="caso:case-1466",
    )

    assert resultado == "novo"
    assert capturado["client_id"] == "client-1466"
    assert capturado["case_id"] == "case-1466"
    assert len(db.get_calls) == 1
    assert db.get_calls[0][1] == "case-1466"


@pytest.mark.asyncio
async def test_resolver_nao_inventa_escopo_para_chave_nao_canonica(monkeypatch):
    from app.services import ai_core_hardening_patch as hardening
    from app.services import ingestion_service

    capturado = {}

    async def fake_upsert(db, **kwargs):
        del db
        capturado.update(kwargs)
        return "novo"

    db = _DBFake(
        SimpleNamespace(
            id="case-nao-deve-ser-consultado",
            client_id="client-nao-deve-vazar",
            deleted_at=None,
            numero_interno="IGNORAR",
        )
    )

    monkeypatch.setattr(ingestion_service, "upsert_documento", fake_upsert)
    monkeypatch.setattr(
        ingestion_service,
        "_ejc_scope_resolver_installed",
        False,
        raising=False,
    )
    hardening._instalar_resolucao_escopo_rag()

    await ingestion_service.upsert_documento(
        db,
        titulo="Outro documento fictício",
        categoria="precedente_interno",
        conteudo="Conteúdo fictício suficiente apenas para testar o escopo.",
        chave_origem="precedente:qualquer",
        fonte="teste",
    )

    assert "client_id" not in capturado
    assert "case_id" not in capturado
    assert db.get_calls == []
