from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_data_room_v4_is_only_a_compatibility_adapter():
    source = _read("app/routers/data_room_v4.py")
    assert "deprecated=True" in source
    assert "criar_data_room" in source
    assert "DataRoomIn" in source
    assert "db.add(room)" not in source
    assert "db.add(sala)" not in source
    assert "DataRoomSala(" not in source.split("async def criar_sala", 1)[1]
    assert "successor-version" in source


def test_teses_v4_is_only_a_compatibility_adapter():
    source = _read("app/routers/teses_v4.py")
    assert "deprecated=True" in source
    assert "criar_tese_canonica" in source
    assert "listar_teses_canonicas" in source
    assert "db.add(t)" not in source
    assert "TeseJuridica(id=" not in source
    assert "successor-version" in source


def test_backfill_is_idempotent_and_non_destructive():
    source = _read("../alembic/versions/114_consolidar_dataroom_teses_v4.py")
    assert 'down_revision = "113_calendar_feed_revocation"' in source
    assert "to_regclass('public.dataroom_salas')" in source
    assert "to_regclass('public.teses_juridicas_v4')" in source
    assert "NOT EXISTS" in source
    assert "DROP TABLE" not in source.upper()
    assert "DELETE FROM" not in source.upper()


def test_legacy_tables_are_read_only_after_backfill():
    data_room = _read("app/routers/data_room_v4.py")
    teses = _read("app/routers/teses_v4.py")
    assert "toda nova leitura e escrita" in data_room
    assert "sem receber novas gravações" in teses
    assert "select(DataRoomSala)" not in data_room
    assert "select(TeseJuridica)" not in teses
