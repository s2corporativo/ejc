"""Regressões do escopo/isolamento RAG no encerramento de caso (#1466).

O fluxo legado de `cases.encerrar_caso` usa `chave_origem="caso:<id>"` e não
passa `client_id` diretamente. O hardening obrigatório do boot deve:

1. resolver o escopo somente pelo caso canônico server-side;
2. jamais inventar escopo para chave/caso inválido;
3. executar a memória acessória em SAVEPOINT;
4. conter falha real do RAG sem invalidar a transação externa do encerramento.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest


class _NestedFake:
    def __init__(self):
        self.entrou = 0
        self.saiu = 0
        self.exc_type = None

    async def __aenter__(self):
        self.entrou += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc, tb
        self.saiu += 1
        self.exc_type = exc_type
        return False


class _DBFake:
    def __init__(self, case):
        self.case = case
        self.get_calls = []
        self.nested = _NestedFake()
        self.begin_nested_calls = 0

    async def get(self, model, entity_id):
        self.get_calls.append((model, entity_id))
        return self.case

    def begin_nested(self):
        self.begin_nested_calls += 1
        return self.nested


def _instalar_sobre(monkeypatch, fake_upsert):
    from app.services import ai_core_hardening_patch as hardening
    from app.services import ingestion_service

    monkeypatch.setattr(ingestion_service, "upsert_documento", fake_upsert)
    monkeypatch.setattr(
        ingestion_service,
        "_ejc_scope_resolver_installed",
        False,
        raising=False,
    )
    hardening._instalar_resolucao_escopo_rag()
    return ingestion_service


@pytest.mark.asyncio
async def test_precedente_caso_resolve_client_case_e_usa_savepoint(monkeypatch):
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
    ingestion_service = _instalar_sobre(monkeypatch, fake_upsert)

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
    assert db.begin_nested_calls == 1
    assert db.nested.entrou == 1
    assert db.nested.saiu == 1
    assert db.nested.exc_type is None


@pytest.mark.asyncio
async def test_resolver_nao_inventa_escopo_para_chave_nao_canonica(monkeypatch):
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
    ingestion_service = _instalar_sobre(monkeypatch, fake_upsert)

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
    assert db.begin_nested_calls == 0


@pytest.mark.asyncio
async def test_caso_deletado_permanece_fail_closed_sem_fallback_global(monkeypatch):
    async def fake_upsert(db, **kwargs):
        del db
        if kwargs.get("categoria") == "precedente_interno" and not kwargs.get("client_id"):
            raise ValueError("categoria restrita exige client_id")
        return "novo"

    db = _DBFake(
        SimpleNamespace(
            id="case-deletado",
            client_id="client-nao-pode-ser-usado",
            deleted_at=object(),
            numero_interno="DELETADO",
        )
    )
    ingestion_service = _instalar_sobre(monkeypatch, fake_upsert)

    with pytest.raises(ValueError, match="exige client_id"):
        await ingestion_service.upsert_documento(
            db,
            titulo="Precedente inválido",
            categoria="precedente_interno",
            conteudo="Conteúdo fictício suficiente apenas para testar o gate.",
            chave_origem="caso:case-deletado",
            fonte="caso:case-deletado",
        )

    assert db.begin_nested_calls == 0


@pytest.mark.asyncio
async def test_falha_rag_valida_reverte_savepoint_e_nao_escapa(monkeypatch, caplog):
    capturado = {}

    async def fake_upsert(db, **kwargs):
        del db
        capturado.update(kwargs)
        raise RuntimeError("detalhe-sensivel-nao-deve-ir-ao-log")

    case = SimpleNamespace(
        id="case-falha-rag",
        client_id="client-falha-rag",
        deleted_at=None,
        numero_interno="EJC-FALHA",
    )
    db = _DBFake(case)
    ingestion_service = _instalar_sobre(monkeypatch, fake_upsert)

    with caplog.at_level(logging.WARNING, logger="ejc.ai.core.hardening"):
        resultado = await ingestion_service.upsert_documento(
            db,
            titulo="Precedente interno fictício",
            categoria="precedente_interno",
            conteudo="Conteúdo fictício suficiente apenas para testar rollback local.",
            chave_origem="caso:case-falha-rag",
            fonte="caso:case-falha-rag",
        )

    assert resultado == "falha_acessoria"
    assert capturado["client_id"] == "client-falha-rag"
    assert capturado["case_id"] == "case-falha-rag"
    assert db.begin_nested_calls == 1
    assert db.nested.exc_type is RuntimeError
    assert "RuntimeError" in caplog.text
    assert "detalhe-sensivel-nao-deve-ir-ao-log" not in caplog.text
