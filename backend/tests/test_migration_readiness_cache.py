from app.core import observability as obs


def test_migration_heads_e_cacheado_por_processo(monkeypatch):
    calls = {"n": 0}

    class FakeScript:
        def get_heads(self):
            return ["161_fee_estornos"]

    def fake_from_config(_cfg):
        calls["n"] += 1
        return FakeScript()

    monkeypatch.setattr(
        "alembic.script.ScriptDirectory.from_config",
        fake_from_config,
    )
    obs._migration_heads.cache_clear()
    try:
        assert obs._migration_heads() == frozenset({"161_fee_estornos"})
        assert obs._migration_heads() == frozenset({"161_fee_estornos"})
        assert calls["n"] == 1
    finally:
        obs._migration_heads.cache_clear()
