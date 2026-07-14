"""Testes de observabilidade: liveness /api/health e no-op do Sentry.

O TestClient NÃO é usado como context manager de propósito: assim os eventos de
lifespan (que tocam o banco) não disparam, e testamos apenas o contrato do
liveness — que por definição não depende de I/O externo.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_liveness_200_e_campos():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "uptime_seconds" in body
    assert isinstance(body["uptime_seconds"], (int, float))
    assert body["uptime_seconds"] >= 0


def test_init_sentry_dsn_vazio_e_noop(monkeypatch):
    """init_sentry() com SENTRY_DSN vazio é no-op e não levanta."""
    from types import SimpleNamespace

    from app.core import observability

    fake = SimpleNamespace(
        SENTRY_DSN="",
        SENTRY_ENVIRONMENT="production",
        SENTRY_TRACES_SAMPLE_RATE=0.0,
        APP_ENV="development",
    )
    monkeypatch.setattr(observability, "get_settings", lambda: fake)

    # Não deve levantar exceção alguma.
    observability.init_sentry()


def test_before_send_scrub_de_dados_sensiveis():
    """O before_send mascara headers e campos sensíveis (LGPD)."""
    from app.core import observability

    event = {
        "request": {
            "headers": {"Authorization": "Bearer abc", "Accept": "*/*"},
            "cookies": "session=xyz",
            "data": {"cpf": "123", "nome": "Fulano", "senha": "s3cr3t"},
        },
        "extra": {"token": "tok-123", "detalhe": "ok"},
    }
    out = observability._before_send(event, None)
    assert out["request"]["headers"]["Authorization"] == "[Filtered]"
    assert out["request"]["headers"]["Accept"] == "*/*"
    assert out["request"]["cookies"] == "[Filtered]"
    assert out["request"]["data"]["cpf"] == "[Filtered]"
    assert out["request"]["data"]["senha"] == "[Filtered]"
    assert out["request"]["data"]["nome"] == "Fulano"
    assert out["extra"]["token"] == "[Filtered]"
    assert out["extra"]["detalhe"] == "ok"
