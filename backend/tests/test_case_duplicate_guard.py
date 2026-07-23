from pathlib import Path


def test_case_creation_has_concurrent_duplicate_guard():
    source = (Path(__file__).parents[1] / "app/routers/cases.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in source
    assert "case_duplicate:" in source
    assert "Já existe caso ativo para este cliente e número processual" in source
    assert "Case.client_id == payload.client_id" in source
    assert "Case.deleted_at.is_(None)" in source
