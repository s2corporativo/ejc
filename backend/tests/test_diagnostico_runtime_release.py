import asyncio
from types import SimpleNamespace

from app.services import diagnostico_service


def test_runtime_release_expoe_sha_e_flags_sem_segredos(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "a" * 40)
    monkeypatch.setenv("EJC_DEPLOYED_AT", "2026-10-01T01:00:00Z")
    settings = SimpleNamespace(
        ENTRADA_UNICA_ENABLED=True,
        FINANCEIRO_ENABLED=False,
        AI_ENABLED=True,
        JUDICIAL_FILING_ENABLED=False,
    )
    item = asyncio.run(diagnostico_service._probe_runtime_release(settings))
    assert item["status"] == "ok"
    assert item["commit"] == "a" * 40
    assert item["feature_flags"]["financeiro"] is False
    assert "password" not in str(item).lower()


def test_backup_expoe_ultima_execucao(monkeypatch):
    from app.services import backup_service

    async def fake_obter_estado(_session):
        return {
            "last_run_at": "2026-10-01T09:00:00+00:00",
            "last_status": "sucesso",
        }

    monkeypatch.setattr(backup_service, "obter_estado", fake_obter_estado)
    settings = SimpleNamespace(APP_ENV="production", BACKUP_ENABLED=True)
    item = asyncio.run(diagnostico_service._probe_backup(object(), settings))
    assert item["backup_enabled"] is True
    assert item["last_status"] == "sucesso"
    assert item["last_run_at"].startswith("2026-10-01T09:00:00")
    assert item["status"] == "ok"
