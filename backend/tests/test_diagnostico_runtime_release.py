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
