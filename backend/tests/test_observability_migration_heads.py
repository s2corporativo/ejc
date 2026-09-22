from __future__ import annotations

import asyncio

from app.core import observability


def test_expected_migration_heads_cacheia_catalogo(monkeypatch):
    chamadas = 0

    def _fake_loader():
        nonlocal chamadas
        chamadas += 1
        return frozenset({"head_teste"})

    observability._expected_migration_heads.cache_clear()
    monkeypatch.setattr(observability, "_load_migration_heads", _fake_loader)
    try:
        assert observability._expected_migration_heads() == frozenset({"head_teste"})
        assert observability._expected_migration_heads() == frozenset({"head_teste"})
        assert chamadas == 1
    finally:
        observability._expected_migration_heads.cache_clear()


async def test_warm_migration_heads_roda_catalogo_fora_do_event_loop(monkeypatch):
    loop_principal = asyncio.get_running_loop()
    loop_visto = None

    def _fake_heads():
        nonlocal loop_visto
        try:
            loop_visto = asyncio.get_running_loop()
        except RuntimeError:
            loop_visto = None
        return frozenset({"head_teste"})

    monkeypatch.setattr(observability, "_expected_migration_heads", _fake_heads)

    assert await observability.warm_migration_heads() is True
    assert loop_visto is None
    assert asyncio.get_running_loop() is loop_principal


async def test_warm_migration_heads_falha_fechado_sem_head(monkeypatch):
    monkeypatch.setattr(
        observability,
        "_expected_migration_heads",
        lambda: frozenset(),
    )
    assert await observability.warm_migration_heads() is False
