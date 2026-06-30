"""Smoke: o app monta e a cadeia de migrations está íntegra (Fases 1 e 2)."""


def test_app_monta_com_rotas():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert len(app.routes) > 300
    # Fase 1 — prefixos corrigidos existem de fato no backend.
    assert any(p.endswith("/auth/refresh") for p in paths)
    assert any(p.endswith("/auth/logout") for p in paths)
    assert any(p.endswith("/pecas/gerar") for p in paths)


def test_alembic_cadeia_integra():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    # Head único = 051 (Fase 3B); a 048 baseline resolve a cadeia (Fase 2).
    assert script.get_heads() == ["051_rag_isolation"]
    # walk_revisions percorre head→base; lança se houver down_revision ausente.
    revs = [r.revision for r in script.walk_revisions()]
    assert revs[-1] == "048_processes"
    assert "049_totp_2fa" in revs and "050_novos_modulos" in revs
