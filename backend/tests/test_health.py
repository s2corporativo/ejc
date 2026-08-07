"""Testes de observabilidade: liveness /api/health.

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
    # O rollback republica o SHA ANTERIOR: sem isso a imagem restaurada
    # anunciaria o commit que acabou de falhar.
    assert "OLD_GIT_SHA" in deploy
    # SHA de origem indeterminado (deploy manual sem TARGET_SHA e sem .git) NÃO
    # pode derrubar o deploy — só desliga a conferência, com aviso. Uma versão
    # anterior desta guarda saía com exit 2 e quebrava o harness de rollback.
    assert "Conferência do commit publicado PULADA" in deploy
    assert "exit 2" not in deploy.split("Commit a publicar")[0].split(
        "GIT_SHA=\"${TARGET_SHA")[-1]
