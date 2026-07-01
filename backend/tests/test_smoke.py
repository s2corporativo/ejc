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
    # Head único = 056 (auditoria 2026-06-30, A1: adiciona processes.is_principal
    # — coluna lida/gravada pelo código mas que só existia via ALTER manual em
    # produção — sobre a 055_rag_isolation, que por sua vez reaplica a Fase 3B
    # sobre a base de produção, que vai até 054_victory_vault). Cadeia única,
    # sem heads divergentes.
    assert script.get_heads() == ["056_processes_is_principal"]
    # walk_revisions percorre head→base; lança se houver down_revision ausente.
    revs = [r.revision for r in script.walk_revisions()]
    assert revs[0] == "056_processes_is_principal"  # head é o primeiro no walk
    assert "055_rag_isolation" in revs             # encaixada após a 055
    assert "054_victory_vault" in revs             # encaixada após a 054 da prod
    assert "049_totp_2fa" in revs and "050_novos_modulos" in revs
