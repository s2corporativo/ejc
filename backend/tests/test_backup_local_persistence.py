from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet

from app.services import backup_service


def _artifact(tmp_path, name: str, payload: bytes = b"ciphertext") -> dict:
    src = tmp_path / (name + ".src")
    src.write_bytes(payload)
    return {
        "nome": name,
        "caminho": str(src),
        "bytes_cifrado": len(payload),
        "bytes_original": 1,
    }


def test_persist_local_set_is_0600_and_survives_source_cleanup(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o700)
    names = [
        "ejc_backup_20260908T050000Z_db.dump.enc",
        "ejc_backup_20260908T050000Z_uploads.tar.gz.enc",
    ]
    arts = [_artifact(tmp_path, n, ("payload-" + n).encode()) for n in names]

    assert backup_service._persistir_artefatos_locais_sync(arts, str(backup_dir)) == 2
    for art in arts:
        os.unlink(art["caminho"])
        final = backup_dir / art["nome"]
        assert final.read_bytes() == ("payload-" + art["nome"]).encode()
        assert (final.stat().st_mode & 0o777) == 0o600
        assert art["local_persistido"] is True


def test_persist_local_rejects_insecure_directory(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o777)
    backup_dir.chmod(0o777)
    art = _artifact(tmp_path, "ejc_backup_20260908T050000Z_db.dump.enc")
    with pytest.raises(Exception, match="gravável por grupo/outros"):
        backup_service._persistir_artefatos_locais_sync([art], str(backup_dir))


def test_persist_local_rolls_back_partial_set_on_failure(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o700)
    names = [
        "ejc_backup_20260908T050000Z_db.dump.enc",
        "ejc_backup_20260908T050000Z_uploads.tar.gz.enc",
    ]
    arts = [_artifact(tmp_path, n, ("payload-" + n).encode()) for n in names]
    real_rename = os.rename
    calls = 0

    def fail_second(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("fixture rename failure")
        return real_rename(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

    monkeypatch.setattr(backup_service.os, "rename", fail_second)
    with pytest.raises(OSError, match="fixture rename failure"):
        backup_service._persistir_artefatos_locais_sync(arts, str(backup_dir))
    assert [p.name for p in backup_dir.iterdir()] == []


def test_local_rotation_only_removes_expired_canonical_encrypted_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o700)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    old = backup_dir / "ejc_backup_20260801T050000Z_db.dump.enc"
    recent = backup_dir / "ejc_backup_20260907T050000Z_db.dump.enc"
    plaintext = backup_dir / "ejc_backup_2026-08-01.sql.gz"
    other = backup_dir / "outro.enc"
    for f in (old, recent, plaintext, other):
        f.write_bytes(b"x")
        f.chmod(0o600)
    old_ts = (now - timedelta(days=40)).timestamp()
    recent_ts = (now - timedelta(days=1)).timestamp()
    os.utime(old, (old_ts, old_ts))
    os.utime(plaintext, (old_ts, old_ts))
    os.utime(other, (old_ts, old_ts))
    os.utime(recent, (recent_ts, recent_ts))

    assert backup_service._rotacionar_local_sync(str(backup_dir), 7, agora=now) == 1
    assert not old.exists()
    assert recent.exists()
    assert plaintext.exists(), "legado em claro exige saneamento explícito, não rotação automática"
    assert other.exists()


def test_local_persisted_artifact_roundtrip_with_backup_key(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o700)
    key = Fernet.generate_key().decode()
    clear = tmp_path / "db.dump"
    clear.write_bytes(b"PGDMP fixture")
    enc = tmp_path / "db.dump.enc"
    size = backup_service.cifrar_arquivo(str(clear), str(enc), key)
    art = {
        "nome": "ejc_backup_20260908T050000Z_db.dump.enc",
        "caminho": str(enc),
        "bytes_cifrado": size,
        "bytes_original": clear.stat().st_size,
    }
    backup_service._persistir_artefatos_locais_sync([art], str(backup_dir))
    restored = tmp_path / "restored.dump"
    backup_service.decifrar_arquivo(str(backup_dir / art["nome"]), str(restored), key)
    assert restored.read_bytes() == clear.read_bytes()
