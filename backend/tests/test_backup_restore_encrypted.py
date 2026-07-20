from __future__ import annotations

import importlib.util
import io
import os
import tarfile
from pathlib import Path
from types import ModuleType

import pytest
from cryptography.fernet import Fernet


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "backup"
    / "validar_restauracao_cifrada.py"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validar_restauracao_cifrada", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def restore_module() -> ModuleType:
    return _load_module()


def _write_tar(path: Path, name: str, *, symlink: bool = False) -> None:
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(name)
        if symlink:
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            archive.addfile(info)
            return
        payload = b"arquivo de teste"
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


def test_validate_pair_accepts_same_timestamp(tmp_path: Path, restore_module: ModuleType):
    db = tmp_path / "ejc_backup_20260720T210000Z_db.dump.enc"
    uploads = tmp_path / "ejc_backup_20260720T210000Z_uploads.tar.gz.enc"
    db.write_bytes(b"db")
    uploads.write_bytes(b"uploads")

    assert restore_module.validate_pair(db, uploads) == "20260720T210000Z"


def test_validate_pair_rejects_mixed_runs(tmp_path: Path, restore_module: ModuleType):
    db = tmp_path / "ejc_backup_20260720T210000Z_db.dump.enc"
    uploads = tmp_path / "ejc_backup_20260720T220000Z_uploads.tar.gz.enc"
    db.write_bytes(b"db")
    uploads.write_bytes(b"uploads")

    with pytest.raises(restore_module.RestoreValidationError, match="execuções diferentes"):
        restore_module.validate_pair(db, uploads)


def test_decrypt_artifact_roundtrip(tmp_path: Path, restore_module: ModuleType):
    key = Fernet.generate_key()
    clear = b"conteudo sensivel ficticio"
    encrypted = tmp_path / "ejc_backup_20260720T210000Z_db.dump.enc"
    decrypted = tmp_path / "db.dump"
    encrypted.write_bytes(Fernet(key).encrypt(clear))

    assert restore_module.decrypt_artifact(encrypted, decrypted, key) == len(clear)
    assert decrypted.read_bytes() == clear


def test_decrypt_artifact_rejects_wrong_key(tmp_path: Path, restore_module: ModuleType):
    encrypted = tmp_path / "ejc_backup_20260720T210000Z_db.dump.enc"
    encrypted.write_bytes(Fernet(Fernet.generate_key()).encrypt(b"dump"))

    with pytest.raises(restore_module.RestoreValidationError, match="chave incorreta"):
        restore_module.decrypt_artifact(
            encrypted,
            tmp_path / "db.dump",
            Fernet.generate_key(),
        )


def test_load_key_prefers_file_without_exposing_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    restore_module: ModuleType,
):
    env_key = Fernet.generate_key().decode()
    file_key = Fernet.generate_key().decode()
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", env_key)
    key_file = tmp_path / "backup.key"
    key_file.write_text(file_key, encoding="utf-8")

    loaded = restore_module.load_fernet_key(key_file)

    assert loaded.decode() == file_key
    assert env_key not in repr(loaded)


def test_inspect_uploads_accepts_only_uploads_root(
    tmp_path: Path,
    restore_module: ModuleType,
):
    safe = tmp_path / "safe.tar.gz"
    _write_tar(safe, "uploads/2026/07/documento.pdf")

    assert restore_module.inspect_uploads_tar(safe) == (1, len(b"arquivo de teste"))


@pytest.mark.parametrize(
    ("name", "symlink"),
    [
        ("../etc/passwd", False),
        ("outro/documento.pdf", False),
        ("uploads/link", True),
    ],
)
def test_inspect_uploads_rejects_unsafe_entries(
    tmp_path: Path,
    restore_module: ModuleType,
    name: str,
    symlink: bool,
):
    unsafe = tmp_path / f"unsafe-{abs(hash((name, symlink)))}.tar.gz"
    _write_tar(unsafe, name, symlink=symlink)

    with pytest.raises(restore_module.RestoreValidationError):
        restore_module.inspect_uploads_tar(unsafe)


def test_disposable_database_guard(
    monkeypatch: pytest.MonkeyPatch,
    restore_module: ModuleType,
):
    production = "postgresql://user:secret@db:5432/ejc_db"
    monkeypatch.setenv("DATABASE_URL_SYNC", production)

    prod_target = restore_module.parse_database_url(production)
    with pytest.raises(restore_module.RestoreValidationError, match="não parece descartável"):
        restore_module.ensure_disposable_target(prod_target)

    test_target = restore_module.parse_database_url(
        "postgresql://user:other@db:5432/ejc_restore_test"
    )
    restore_module.ensure_disposable_target(test_target)


def test_guard_rejects_disposable_name_when_same_as_configured_production(
    monkeypatch: pytest.MonkeyPatch,
    restore_module: ModuleType,
):
    url = "postgresql://user:secret@db:5432/ejc_restore_test"
    monkeypatch.setenv("DATABASE_URL", url)
    target = restore_module.parse_database_url(url)

    with pytest.raises(restore_module.RestoreValidationError, match="coincide"):
        restore_module.ensure_disposable_target(target)


def test_database_password_only_enters_subprocess_environment(
    restore_module: ModuleType,
):
    target = restore_module.parse_database_url(
        "postgresql://user:senha%40segura@localhost:5432/ejc_restore_test"
    )
    env = restore_module.database_command_env(target)

    assert target.password == "senha@segura"
    assert env["PGPASSWORD"] == "senha@segura"
    assert "senha@segura" not in str(target.identity)


def test_missing_key_error_does_not_echo_environment(
    monkeypatch: pytest.MonkeyPatch,
    restore_module: ModuleType,
):
    monkeypatch.delenv("BACKUP_ENCRYPTION_KEY", raising=False)

    with pytest.raises(restore_module.RestoreValidationError) as exc:
        restore_module.load_fernet_key()

    assert "BACKUP_ENCRYPTION_KEY" in str(exc.value)
    assert os.environ.get("DATABASE_URL", "") not in str(exc.value)
