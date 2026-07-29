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


def test_health_expoe_o_commit_publicado(monkeypatch):
    """Prova de qual código está no ar (consolidação 2026-07-29).

    `GIT_SHA` era lido por app_version() mas NINGUÉM o definia — nem o compose,
    nem o script de deploy — então produção respondia sempre "dev" e não havia
    como distinguir "a alteração não foi publicada" de "a alteração não
    funciona". O deploy agora injeta o SHA e confere este campo antes de dar o
    deploy por concluído."""
    sha = "0123456789abcdef0123456789abcdef01234567"
    monkeypatch.setenv("GIT_SHA", sha)
    body = client.get("/api/health").json()
    assert body["commit"] == sha


def test_health_sem_git_sha_declara_desconhecido(monkeypatch):
    """Nunca omite o campo: ausência é declarada, não silenciosa."""
    monkeypatch.delenv("GIT_SHA", raising=False)
    body = client.get("/api/health").json()
    assert body["commit"] == "desconhecido"


def test_deploy_injeta_e_confere_o_commit():
    """Guarda de wiring: sem isto o campo existiria mas ninguém o preencheria —
    exatamente o defeito que este teste cobre."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    compose = (raiz / "docker-compose.yml").read_text(encoding="utf-8")
    assert "GIT_SHA: ${GIT_SHA:-}" in compose

    deploy = (raiz / "scripts" / "deploy_vps_safe.sh").read_text(encoding="utf-8")
    assert "export GIT_SHA" in deploy
    assert '"commit"' in deploy, "o deploy precisa conferir o commit no /api/health"


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
