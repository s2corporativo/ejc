from __future__ import annotations

import importlib.util
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "backup"
    / "validar_restauracao_cifrada.py"
)


def _load_module() -> ModuleType:
    module_name = "validar_restauracao_cifrada_export_tests"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def restore_module() -> ModuleType:
    return _load_module()


def test_guard_compara_banco_fisico_mesmo_com_usuario_diferente(
    monkeypatch: pytest.MonkeyPatch,
    restore_module: ModuleType,
):
    monkeypatch.setenv(
        "DATABASE_URL_SYNC",
        "postgresql://app:segredo@db:5432/ejc_restore_test",
    )
    target = restore_module.parse_database_url(
        "postgresql://outro:outra@db:5432/ejc_restore_test"
    )

    with pytest.raises(restore_module.RestoreValidationError, match="coincide"):
        restore_module.ensure_disposable_target(target)


def test_export_clear_artifacts_uses_permissions_restritas(
    tmp_path: Path,
    restore_module: ModuleType,
):
    db = tmp_path / "source.dump"
    uploads = tmp_path / "source.tar.gz"
    db.write_bytes(b"dump ficticio")
    uploads.write_bytes(b"uploads ficticios")
    output = tmp_path / "clear"

    exported = restore_module.export_clear_artifacts(db, uploads, output)

    assert Path(exported["db.dump"]).read_bytes() == b"dump ficticio"
    assert Path(exported["uploads.tar.gz"]).read_bytes() == b"uploads ficticios"
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "db.dump").stat().st_mode) == 0o600
    assert stat.S_IMODE((output / "uploads.tar.gz").stat().st_mode) == 0o600


def test_export_clear_artifacts_recusa_diretorio_nao_vazio(
    tmp_path: Path,
    restore_module: ModuleType,
):
    db = tmp_path / "source.dump"
    db.write_bytes(b"dump")
    output = tmp_path / "clear"
    output.mkdir()
    (output / "existente.txt").write_text("não sobrescrever", encoding="utf-8")

    with pytest.raises(restore_module.RestoreValidationError, match="deve estar vazio"):
        restore_module.export_clear_artifacts(db, None, output)
