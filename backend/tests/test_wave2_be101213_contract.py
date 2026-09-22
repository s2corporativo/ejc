from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_be10_tabelas_operacionais_tem_migration_e_model():
    migration = (ROOT / "backend/alembic/versions/162_operational_state_tables.py").read_text()
    models = (ROOT / "backend/app/models/operational_state.py").read_text()
    for table in (
        "indices_bcb_cache",
        "indices_bcb_cache_meta",
        "google_drive_sync_state",
        "infosimples_uso",
        "radar_legislativo_visto",
        "transparencia_cache",
        "backup_drive_state",
    ):
        assert table in migration
        assert f'__tablename__ = "{table}"' in models


def test_be12_leitura_canonica_e_write_through_temporario():
    service = (ROOT / "backend/app/services/processo_service.py").read_text()
    assert "async def processo_principal" in service
    assert "process_repository.principal" in service
    assert "_sync_case_legacy" in service
    assert "A fonte de verdade é `processes`" in service


def test_be13_backfill_e_dry_run_por_default():
    script = (ROOT / "scripts/backfill_fee_ledger.py").read_text()
    assert "if not args.apply" in script
    assert "NOT EXISTS (SELECT 1 FROM fee_payments" in script
    assert "fees.status" not in script or "não altera ``fees.status``" in script
    assert "ON CONFLICT DO NOTHING" in script
