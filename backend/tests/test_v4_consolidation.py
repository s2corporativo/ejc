from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).parents[1]


def _source(relative: str) -> str:
    return (_ROOT / relative).read_text(encoding="utf-8")


def test_data_room_v4_is_compatibility_adapter_only():
    source = _source("app/routers/data_room_v4.py")
    assert "deprecated=True" in source
    assert 'rel="successor-version"' in source
    assert "DataRoom(" in source
    assert "DataRoomSala(" not in source
    assert "select(DataRoom)" in source
    assert "select(DataRoomSala)" not in source


def test_teses_v4_is_compatibility_adapter_only():
    source = _source("app/routers/teses_v4.py")
    assert "deprecated=True" in source
    assert 'rel="successor-version"' in source
    assert "Tese(" in source
    assert "TeseJuridica(" not in source
    assert "select(Tese)" in source
    assert "select(TeseJuridica)" not in source


def test_migration_preserves_sources_and_legacy_metadata():
    source = _source("alembic/versions/110_consolidar_dataroom_teses_v4.py")
    upper = source.upper()
    assert "LEGACY_EXPIRA_EM" in upper
    assert "LEGACY_PUBLICA" in upper
    assert "LEGACY_VENCEDORA" in upper
    assert "DROP TABLE" not in upper
    assert "DELETE FROM DATAROOM_SALAS" not in upper
    assert "DELETE FROM TESES_JURIDICAS_V4" not in upper
    # Não fabrica histórico de uso/vitória a partir do booleano antigo.
    assert "0,\n                    0,\n                    0,\n                    src.taxa_sucesso" in source


def test_compatibility_fields_do_not_enable_public_access():
    model = _source("app/models/data_room.py")
    router = _source("app/routers/data_room_v4.py")
    assert "legacy_publica" in model
    assert "DataRoomLink" in model
    assert "legacy_publica=False" in router
    assert "token =" not in router
