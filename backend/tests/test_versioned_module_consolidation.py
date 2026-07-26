from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_data_room_v4_router_foi_removido():
    """O shim de compatibilidade `data_room_v4` (`/api/data-room-v4`) foi
    removido por completo: investigação de uso (frontend, backend, docs,
    integrações) não encontrou nenhum chamador real, só o próprio comentário
    genérico "para favoritos e integrações históricas" sem exemplo concreto.
    A tabela `dataroom_salas` permanece no banco apenas como origem histórica
    do backfill da migration 114 — não é dropada aqui (ver docstring da 114:
    retirada física exige telemetria/backup/homologação prévios)."""
    assert not (ROOT / "app/routers/data_room_v4.py").exists()


def test_teses_v4_is_only_a_compatibility_adapter():
    source = _read("app/routers/teses_v4.py")
    assert "deprecated=True" in source
    assert "criar_tese_canonica" in source
    assert "listar_teses_canonicas" in source
    assert "db.add(t)" not in source
    assert "TeseJuridica(id=" not in source
    assert "successor-version" in source


def test_backfill_is_idempotent_and_non_destructive():
    source = _read("alembic/versions/114_consolidar_dataroom_teses_v4.py")
    assert 'down_revision = "113_calendar_feed_revocation"' in source
    assert 'deployment_policy = "additive_data_backfill"' in source
    assert 'data_backfill_targets = ("data_rooms", "teses")' in source
    assert "to_regclass('public.dataroom_salas')" in source
    assert "to_regclass('public.teses_juridicas_v4')" in source
    assert "NOT EXISTS" in source
    assert "DROP TABLE" not in source.upper()
    assert "DELETE FROM" not in source.upper()
    assert "UPDATE " not in source.upper()


def test_orphan_legacy_client_does_not_break_data_room_backfill():
    source = _read("alembic/versions/114_consolidar_dataroom_teses_v4.py")
    assert "LEFT JOIN clients cli ON cli.id = src.client_id" in source
    assert "CASE WHEN cli.id IS NOT NULL THEN src.client_id ELSE NULL END" in source
    assert "Vínculo histórico com cliente inexistente" in source


def test_legacy_tables_are_read_only_after_backfill():
    """Teses v4 segue como adaptador de compatibilidade somente leitura. Data
    Room v4 foi removido por completo (ver test_data_room_v4_router_foi_removido),
    o que é uma garantia ainda mais forte do que "somente leitura"."""
    teses = _read("app/routers/teses_v4.py")
    assert "sem receber novas gravações" in teses
    assert "select(TeseJuridica)" not in teses
