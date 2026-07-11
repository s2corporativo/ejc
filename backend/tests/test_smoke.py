"""Smoke: o app monta e a cadeia de migrations está íntegra (Fases 1 e 2)."""


def test_app_monta_com_rotas():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert len(app.routes) > 300
    assert any(p.endswith("/auth/refresh") for p in paths)
    assert any(p.endswith("/auth/logout") for p in paths)
    assert any(p.endswith("/pecas/gerar") for p in paths)
    assert any(p.endswith("/ai/traduzir-andamento") for p in paths)
    assert any(p.endswith("/ai/gerar-minuta") for p in paths)
    assert "/api/system-modules/settings" in paths
    assert "/api/notifications/preferences" in paths
    assert "/api/notifications/push/subscriptions" in paths


def test_alembic_cadeia_integra():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["084_automacoes_cliente"]
    revs = [r.revision for r in script.walk_revisions()]
    assert revs[-1] == "001_inicial"
    assert "048_processes" in revs
    assert "049_totp_2fa" in revs and "050_novos_modulos" in revs
    assert "059_archiving_cases_processes" in revs
    assert "060_client_anonimizacao" in revs
    assert "061_client_pii_encriptado" in revs
    assert "062_redesign_tables" in revs
    assert "063_workflow_sla_atrasado" in revs
    assert "064_drive_columns" in revs
    assert "065_djen_prazo_assistido" in revs
    assert "066_ai_log_feedback" in revs
    assert "067_v4_dataroom_teses" in revs
    assert "068_rag_versionamento" in revs
    assert "069_api_keys" in revs
    assert "070_ai_log_critica_adversarial" in revs
    assert "071_sociedades_cliente" in revs
    assert "072_lgpd_registros" in revs
    assert "073_provas" in revs
    assert "074_remove_licitacao_admin_tipo" in revs
    assert "075_fk_partial_unique_dtnasc" in revs
    assert "076_fk_hot_path_indexes" in revs
    assert "077_deadline_confirmado_doc" in revs
    assert "078_seed_kanban_columns" in revs
    assert "079_client_hash_partial_deleted" in revs
    assert "081_system_module_settings" in revs
    assert "082_notification_preferences" in revs
