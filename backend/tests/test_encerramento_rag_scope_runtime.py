"""Regressões de escopo do precedente interno no encerramento (#1466)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest


class _DBFake:
    def __init__(self, case):
        self.case = case
        self.get_calls: list[tuple[object, str]] = []

    async def get(self, model, entity_id):
        self.get_calls.append((model, entity_id))
        return self.case


def _instalar_sobre(monkeypatch, fake_upsert):
    from app.services import ai_core_hardening_patch as hardening
    from app.services import ingestion_service

    monkeypatch.setattr(ingestion_service, "upsert_documento", fake_upsert)
    monkeypatch.setattr(
        ingestion_service, "_ejc_scope_resolver_installed", False, raising=False
    )
    hardening._instalar_resolucao_escopo_rag()
    return ingestion_service


@pytest.mark.asyncio
async def test_precedente_resolve_escopo_pelo_caso_canonico(monkeypatch):
    capturado = {}

    async def fake_upsert(db, **kwargs):
        del db
        capturado.update(kwargs)
        return "novo"

    case = SimpleNamespace(
        id="case-1466", client_id="client-1466", deleted_at=None
    )
    db = _DBFake(case)
    ingestion = _instalar_sobre(monkeypatch, fake_upsert)

    resultado = await ingestion.upsert_documento(
        db,
        titulo="Precedente fictício",
        categoria="precedente_interno",
        conteudo="Conteúdo sintético",
        chave_origem="caso:case-1466",
        fonte="caso:case-1466",
    )

    assert resultado == "novo"
    assert capturado["client_id"] == "client-1466"
    assert capturado["case_id"] == "case-1466"
    assert db.get_calls[0][1] == "case-1466"


@pytest.mark.asyncio
async def test_escopo_explicito_divergente_e_bloqueado_antes_do_upsert(monkeypatch):
    chamado = False

    async def fake_upsert(db, **kwargs):
        nonlocal chamado
        del db, kwargs
        chamado = True

    case = SimpleNamespace(
        id="case-seguro", client_id="client-correto", deleted_at=None
    )
    db = _DBFake(case)
    ingestion = _instalar_sobre(monkeypatch, fake_upsert)

    with pytest.raises(ValueError, match="client_id divergente"):
        await ingestion.upsert_documento(
            db,
            titulo="Precedente adulterado",
            categoria="precedente_interno",
            conteudo="Conteúdo sintético",
            chave_origem="caso:case-seguro",
            fonte="caso:case-seguro",
            client_id="client-incorreto",
            case_id="case-seguro",
        )

    assert chamado is False


@pytest.mark.asyncio
async def test_case_id_explicito_divergente_e_bloqueado(monkeypatch):
    chamado = False

    async def fake_upsert(db, **kwargs):
        nonlocal chamado
        del db, kwargs
        chamado = True

    case = SimpleNamespace(
        id="case-correto", client_id="client-correto", deleted_at=None
    )
    ingestion = _instalar_sobre(monkeypatch, fake_upsert)

    with pytest.raises(ValueError, match="case_id divergente"):
        await ingestion.upsert_documento(
            _DBFake(case),
            titulo="Precedente adulterado",
            categoria="precedente_interno",
            conteudo="Conteúdo sintético",
            chave_origem="caso:case-correto",
            fonte="caso:case-correto",
            client_id="client-correto",
            case_id="outro-case",
        )

    assert chamado is False


@pytest.mark.asyncio
async def test_caso_deletado_falha_fechado_sem_fallback_global(monkeypatch):
    chamado = False

    async def fake_upsert(db, **kwargs):
        nonlocal chamado
        del db, kwargs
        chamado = True

    case = SimpleNamespace(
        id="case-deletado", client_id="client-1", deleted_at=object()
    )
    ingestion = _instalar_sobre(monkeypatch, fake_upsert)

    with pytest.raises(ValueError, match="caso canônico inválido"):
        await ingestion.upsert_documento(
            _DBFake(case),
            titulo="Precedente inválido",
            categoria="precedente_interno",
            conteudo="Conteúdo sintético",
            chave_origem="caso:case-deletado",
            fonte="caso:case-deletado",
        )

    assert chamado is False


@pytest.mark.asyncio
async def test_chave_nao_canonica_nao_ganha_escopo_inventado(monkeypatch):
    capturado = {}

    async def fake_upsert(db, **kwargs):
        del db
        capturado.update(kwargs)
        return "novo"

    db = _DBFake(None)
    ingestion = _instalar_sobre(monkeypatch, fake_upsert)
    await ingestion.upsert_documento(
        db,
        titulo="Outro documento",
        categoria="precedente_interno",
        conteudo="Conteúdo sintético",
        chave_origem="precedente:qualquer",
        fonte="teste",
    )

    assert "client_id" not in capturado
    assert "case_id" not in capturado
    assert db.get_calls == []
