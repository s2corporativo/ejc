"""Smoke: o app monta e a cadeia de migrations está íntegra (Fases 1 e 2)."""


def test_app_monta_com_rotas():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert len(app.routes) > 300
    # Fase 1 — prefixos corrigidos existem de fato no backend.
    assert any(p.endswith("/auth/refresh") for p in paths)
    assert any(p.endswith("/auth/logout") for p in paths)
    assert any(p.endswith("/pecas/gerar") for p in paths)
    # Bloco 1 (Etapa 4): ia_extra passou a ser montado — as 5 rotas que o
    # frontend chama (AssistenteIA, ExplicarMov, NoticiasCard…) não podem
    # voltar a ficar 404 por o router deixar de ser incluído em main.py.
    assert any(p.endswith("/ai/traduzir-andamento") for p in paths)
    assert any(p.endswith("/ai/gerar-minuta") for p in paths)


def test_alembic_cadeia_integra():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    # Head único da cadeia atual.
    assert script.get_heads() == ["059_archiving_cases_processes"]
    # walk_revisions percorre head→base; lança se houver down_revision ausente.
    revs = [r.revision for r in script.walk_revisions()]
    assert revs[-1] == "001_inicial"
    assert "048_processes" in revs
    assert "049_totp_2fa" in revs and "050_novos_modulos" in revs
    assert "059_archiving_cases_processes" in revs
