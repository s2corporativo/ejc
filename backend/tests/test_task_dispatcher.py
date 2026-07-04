# ── tests/test_task_dispatcher.py ────────────────────────────────────────────
# Dispatcher único de indexação (Fase 3A): Celery quando habilitado E Redis
# alcançável; senão BackgroundTasks (comportamento pré-Celery preservado).
import pytest
from fastapi import BackgroundTasks

from app.core.config import get_settings
from app.tasks import dispatcher
from app.tasks.dispatcher import agendar_indexacao


@pytest.fixture
def settings():
    return get_settings()


async def test_fallback_background_quando_celery_desligado(settings, monkeypatch):
    """CELERY_ENABLED=False (default) → agenda em BackgroundTasks, nunca toca Redis."""
    monkeypatch.setattr(settings, "CELERY_ENABLED", False)

    async def _explode(url, timeout=1.0):  # Redis NÃO pode ser consultado
        raise AssertionError("não deveria pingar o Redis com Celery desligado")
    monkeypatch.setattr(dispatcher, "_redis_alcancavel", _explode)

    bt = BackgroundTasks()
    mecanismo = await agendar_indexacao("doc-123", bt)

    assert mecanismo == "background"
    assert len(bt.tasks) == 1
    from app.routers.rag import _indexar_doc_bg
    assert bt.tasks[0].func is _indexar_doc_bg
    assert bt.tasks[0].args == ("doc-123",)


async def test_fallback_background_quando_redis_inalcancavel(settings, monkeypatch):
    """CELERY_ENABLED=True mas Redis fora do ar → fallback gracioso."""
    monkeypatch.setattr(settings, "CELERY_ENABLED", True)

    async def _fora_do_ar(url, timeout=1.0):
        return False
    monkeypatch.setattr(dispatcher, "_redis_alcancavel", _fora_do_ar)

    bt = BackgroundTasks()
    assert await agendar_indexacao("doc-456", bt) == "background"
    assert len(bt.tasks) == 1


async def test_usa_celery_quando_habilitado_e_redis_ok(settings, monkeypatch):
    """CELERY_ENABLED=True + Redis OK → task.delay; nada em BackgroundTasks."""
    monkeypatch.setattr(settings, "CELERY_ENABLED", True)

    async def _ok(url, timeout=1.0):
        return True
    monkeypatch.setattr(dispatcher, "_redis_alcancavel", _ok)

    enfileirados: list[str] = []
    from app.tasks import rag_tasks
    monkeypatch.setattr(rag_tasks.indexar_documento_task, "delay",
                        lambda doc_id: enfileirados.append(doc_id))

    bt = BackgroundTasks()
    assert await agendar_indexacao("doc-789", bt) == "celery"
    assert enfileirados == ["doc-789"]
    assert bt.tasks == []


async def test_erro_no_enfileiramento_cai_para_background(settings, monkeypatch):
    """Redis pinga mas o broker falha na hora do delay → BackgroundTasks."""
    monkeypatch.setattr(settings, "CELERY_ENABLED", True)

    async def _ok(url, timeout=1.0):
        return True
    monkeypatch.setattr(dispatcher, "_redis_alcancavel", _ok)

    from app.tasks import rag_tasks

    def _quebra(doc_id):
        raise ConnectionError("broker caiu")
    monkeypatch.setattr(rag_tasks.indexar_documento_task, "delay", _quebra)

    bt = BackgroundTasks()
    assert await agendar_indexacao("doc-000", bt) == "background"
    assert len(bt.tasks) == 1


async def test_redis_inalcancavel_retorna_false_sem_excecao():
    """Ping em endereço inválido nunca propaga exceção."""
    assert await dispatcher._redis_alcancavel(
        "redis://127.0.0.1:1/0", timeout=0.2
    ) is False
