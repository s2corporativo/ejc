# ── tests/test_readiness.py ───────────────────────────────────────────────────
# Endpoint /api/health/ready: o STATUS HTTP reflete a prontidão (DB crítico →
# 503), ao contrário do /api/health (liveness, sempre 200). Chamamos a função
# diretamente (sem TestClient) para não subir o lifespan/scheduler no teste.
import json

from app import main
from app.core.config import get_settings


async def _chamar():
    resp = await main.readiness()
    return resp.status_code, json.loads(resp.body)


async def test_ready_quando_db_ok(monkeypatch):
    async def _db_ok():
        return True
    monkeypatch.setattr(main, "check_db", _db_ok)
    monkeypatch.setattr("app.services.embedding_service.disponivel", lambda: True)

    status, corpo = await _chamar()
    assert status == 200
    assert corpo["status"] == "ready"
    assert corpo["checks"]["database"] is True
    assert corpo["checks"]["embeddings"] is True


async def test_not_ready_retorna_503_quando_db_fora(monkeypatch):
    """DB fora do ar → 503 (o monitor externo precisa DETECTAR a queda; o
    /api/health devolvia 200 'degraded' e passava batido)."""
    async def _db_down():
        return False
    monkeypatch.setattr(main, "check_db", _db_down)
    monkeypatch.setattr("app.services.embedding_service.disponivel", lambda: False)

    status, corpo = await _chamar()
    assert status == 503
    assert corpo["status"] == "not_ready"
    assert corpo["checks"]["database"] is False


async def test_redis_nao_checado_quando_desabilitado(monkeypatch):
    """Sem Celery nem rate limit em Redis, a checagem de Redis é 'não utilizado'
    (None) — não penaliza nem tenta conectar."""
    async def _db_ok():
        return True
    monkeypatch.setattr(main, "check_db", _db_ok)
    monkeypatch.setattr("app.services.embedding_service.disponivel", lambda: True)
    monkeypatch.setattr(get_settings(), "CELERY_ENABLED", False)
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_REDIS_ENABLED", False)

    _, corpo = await _chamar()
    assert corpo["checks"]["redis"] is None


async def test_redis_checado_quando_habilitado(monkeypatch):
    """Com Redis habilitado, a prontidão reporta a reachability (informativa —
    não derruba o 200 enquanto o DB estiver ok)."""
    async def _db_ok():
        return True
    monkeypatch.setattr(main, "check_db", _db_ok)
    monkeypatch.setattr("app.services.embedding_service.disponivel", lambda: True)
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_REDIS_ENABLED", True)

    async def _redis_ok(_url, timeout=1.0):
        return True
    monkeypatch.setattr("app.tasks.dispatcher._redis_alcancavel", _redis_ok)

    status, corpo = await _chamar()
    assert status == 200
    assert corpo["checks"]["redis"] is True
