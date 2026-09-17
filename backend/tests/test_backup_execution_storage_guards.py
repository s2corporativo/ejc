from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.services import backup_execution_service


class _DummyLock:
    def __init__(self) -> None:
        self.released = False

    def release(self) -> None:
        self.released = True


def _touch(path, *, when: datetime) -> None:
    path.write_bytes(b"x")
    path.chmod(0o600)
    ts = when.timestamp()
    os.utime(path, (ts, ts))


def test_pre_rotation_removes_expired_older_sets_but_preserves_latest(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o700)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)

    old_a = backup_dir / "ejc_backup_20260801T050000Z_db.dump.enc"
    old_b = backup_dir / "ejc_backup_20260801T050000Z_uploads.tar.gz.enc"
    newest_a = backup_dir / "ejc_backup_20260802T050000Z_db.dump.enc"
    newest_b = backup_dir / "ejc_backup_20260802T050000Z_uploads.tar.gz.enc"
    unrelated = backup_dir / "outro.enc"

    for path in (old_a, old_b):
        _touch(path, when=now - timedelta(days=40))
    for path in (newest_a, newest_b):
        _touch(path, when=now - timedelta(days=39))
    _touch(unrelated, when=now - timedelta(days=100))

    removed = backup_execution_service._pre_rotacionar_local_sync(
        str(backup_dir), 7, agora=now
    )

    assert removed == 2
    assert not old_a.exists() and not old_b.exists()
    assert newest_a.exists() and newest_b.exists(), "último conjunto conhecido deve sobreviver à pré-rotação"
    assert unrelated.exists(), "arquivo fora do contrato EJC nunca é removido"


def test_cleanup_removes_only_canonical_temp_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o700)

    stale = backup_dir / ".ejc_backup_20260908T050000Z_db.dump.enc.123.456.tmp"
    other_tmp = backup_dir / ".outro.tmp"
    canonical = backup_dir / "ejc_backup_20260908T050000Z_db.dump.enc"
    for path in (stale, other_tmp, canonical):
        path.write_bytes(b"x")
        path.chmod(0o600)

    removed = backup_execution_service._cleanup_temporarios_locais_sync(str(backup_dir))

    assert removed == 1
    assert not stale.exists()
    assert other_tmp.exists()
    assert canonical.exists()


@pytest.mark.asyncio
async def test_invalid_retention_fails_closed_before_engine(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o700)
    lock = _DummyLock()
    called = False

    monkeypatch.setattr(backup_execution_service.settings, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(backup_execution_service.settings, "BACKUP_RETENTION_DAYS", 0)
    monkeypatch.setattr(backup_execution_service, "acquire_backup_lock", lambda _path: lock)

    async def fake_engine(*_args, **_kwargs):
        nonlocal called
        called = True
        return {"ok": True, "status": "sucesso"}

    monkeypatch.setattr(backup_execution_service.backup_service, "executar_backup", fake_engine)

    result = await backup_execution_service.executar_backup_exclusivo(object(), origem="teste")

    assert result["ok"] is False
    assert result["status"] == "erro_configuracao"
    assert called is False
    assert lock.released is True


@pytest.mark.asyncio
async def test_failed_engine_leaves_no_canonical_temp_after_return(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o700)
    lock = _DummyLock()

    monkeypatch.setattr(backup_execution_service.settings, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(backup_execution_service.settings, "BACKUP_RETENTION_DAYS", 7)
    monkeypatch.setattr(backup_execution_service, "acquire_backup_lock", lambda _path: lock)

    async def fake_engine(*_args, **_kwargs):
        leaked = backup_dir / ".ejc_backup_20260908T050000Z_db.dump.enc.777.888.tmp"
        leaked.write_bytes(b"partial")
        leaked.chmod(0o600)
        return {"ok": False, "status": "erro", "avisos": []}

    monkeypatch.setattr(backup_execution_service.backup_service, "executar_backup", fake_engine)

    result = await backup_execution_service.executar_backup_exclusivo(object(), origem="teste")

    assert result["ok"] is False
    assert not any(path.name.endswith(".tmp") for path in backup_dir.iterdir())
    assert result["temporarios_locais_saneados_pos"] == 1
    assert lock.released is True
