"""Regressões offline do hook pós-vínculo de documento existente."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks


@pytest.mark.asyncio
async def test_vinculo_com_ocr_agenda_analise_compartilhada(monkeypatch):
    from app.routers import kit_documental

    async def _vincular(*_args, **_kwargs):
        return {"ok": True, "alterado": True, "document_id": "doc-1"}

    async def _ocr(*_args, **_kwargs):
        return "texto OCR suficiente para análise estratégica"

    async def _hook(*_args, **_kwargs):
        return None

    monkeypatch.setattr(kit_documental, "vincular_documento_existente", _vincular)
    monkeypatch.setattr(kit_documental, "obter_ocr_documento_vinculado", _ocr)
    monkeypatch.setattr(kit_documental, "analisar_documento_bg", _hook)

    background_tasks = BackgroundTasks()
    out = await kit_documental.vincular_documento_ao_caso(
        "case-1",
        "doc-1",
        background_tasks,
        db=object(),
        cu=SimpleNamespace(id="user-1"),
    )

    assert out["alterado"] is True
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is _hook
    assert task.args == ("case-1", "texto OCR suficiente para análise estratégica", "doc-1", "user-1")


@pytest.mark.asyncio
async def test_vinculo_idempotente_nao_reagenda_analise(monkeypatch):
    from app.routers import kit_documental

    async def _vincular(*_args, **_kwargs):
        return {"ok": True, "alterado": False, "document_id": "doc-1"}

    async def _ocr(*_args, **_kwargs):
        raise AssertionError("OCR não deve ser consultado em vínculo idempotente")

    monkeypatch.setattr(kit_documental, "vincular_documento_existente", _vincular)
    monkeypatch.setattr(kit_documental, "obter_ocr_documento_vinculado", _ocr)

    background_tasks = BackgroundTasks()
    out = await kit_documental.vincular_documento_ao_caso(
        "case-1",
        "doc-1",
        background_tasks,
        db=object(),
        cu=SimpleNamespace(id="user-1"),
    )

    assert out["alterado"] is False
    assert background_tasks.tasks == []
