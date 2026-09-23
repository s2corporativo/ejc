"""Contratos da primeira fatia W8.2: job assíncrono de análise de caso."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.models.user import UserRole
from app.routers import ai
from app.services.ai_async_jobs import AIAsyncJobStore


def test_store_e_idempotente_por_usuario_e_request_id():
    store = AIAsyncJobStore(ttl_seconds=900)
    first, created = store.create_or_get(
        user_id="u1", request_id="req-1", case_id="case-1"
    )
    again, created_again = store.create_or_get(
        user_id="u1", request_id="req-1", case_id="case-1"
    )

    assert created is True
    assert created_again is False
    assert again.task_id == first.task_id


def test_store_nao_reutiliza_request_id_de_outro_usuario():
    store = AIAsyncJobStore(ttl_seconds=900)
    first, _ = store.create_or_get(user_id="u1", request_id="req-1", case_id=None)
    with pytest.raises(HTTPException) as exc:
        store.get_for_user(first.task_id, "u2")
    assert exc.value.status_code == 404


def test_store_rejeita_mesmo_request_id_para_outro_caso():
    store = AIAsyncJobStore(ttl_seconds=900)
    store.create_or_get(user_id="u1", request_id="req-1", case_id="case-1")
    with pytest.raises(HTTPException) as exc:
        store.create_or_get(user_id="u1", request_id="req-1", case_id="case-2")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_porta_async_desligada_por_padrao(monkeypatch):
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(IA_ANALISE_ASYNC_ENABLED=False),
    )
    req = SimpleNamespace(descricao_fatos="fatos suficientes para o teste", case_id=None)
    user = SimpleNamespace(id="u1", role=UserRole.advogado)

    with pytest.raises(HTTPException) as exc:
        await ai.analisar_async(req, BackgroundTasks(), object(), user)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_porta_async_cria_job_e_nao_duplica_background(monkeypatch):
    settings = SimpleNamespace(
        IA_ANALISE_ASYNC_ENABLED=True,
        IA_ANALISE_ASYNC_TTL_SEGUNDOS=900,
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    from app.services import ai_async_jobs
    ai_async_jobs._store = AIAsyncJobStore(ttl_seconds=900)

    req = SimpleNamespace(
        descricao_fatos="fatos suficientes para a análise assíncrona",
        case_id=None,
        request_id="request-w82",
    )
    user = SimpleNamespace(id="u1", role=UserRole.advogado)
    background = BackgroundTasks()

    first = await ai.analisar_async(req, background, object(), user)
    second = await ai.analisar_async(req, background, object(), user)

    assert first["status"] == "queued"
    assert second["task_id"] == first["task_id"]
    assert len(background.tasks) == 1


@pytest.mark.asyncio
async def test_worker_publica_resultado_sem_expor_erro_interno(monkeypatch):
    from app.services import ai_async_jobs
    store = AIAsyncJobStore(ttl_seconds=900)
    ai_async_jobs._store = store
    job, _ = store.create_or_get(user_id="u1", request_id="req", case_id=None)

    async def falhar(*args):
        raise RuntimeError("conteúdo sensível interno")

    monkeypatch.setattr(ai, "analisar", falhar)
    await ai._executar_analise_async(job.task_id, object(), object(), SimpleNamespace(id="u1"))

    status = store.public(store.get_for_user(job.task_id, "u1"))
    assert status["status"] == "failed"
    assert status["erro"] == "Falha ao executar análise"
    assert "sensível" not in str(status)
