from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "ci_evidence.py"
AUTH_SCRIPT = ROOT / "scripts" / "github-app-auth.sh"


def _load_module():
    spec = importlib.util.spec_from_file_location("ci_evidence", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_success_pointer_e_hashes_detectam_adulteracao(tmp_path: Path):
    ev = _load_module()
    sha = "a" * 40
    root = tmp_path / "evidence"
    attempt = ev.start_attempt(root, sha, "feature/x", 42)
    log = attempt / "backend.log"
    log.write_bytes(b"ok\n" * 4096)

    summary = ev.finish_attempt(
        attempt,
        root / sha,
        sha,
        "feature/x",
        42,
        "success",
        None,
        0,
        True,
    )

    assert summary.is_file()
    assert ev.verify_success(root / sha, sha) is True

    # A evidência é content-addressed: qualquer alteração posterior invalida o gate.
    log.write_bytes(log.read_bytes() + b"tamper\n")
    assert ev.verify_success(root / sha, sha) is False


def test_failure_nunca_atualiza_latest_success(tmp_path: Path):
    ev = _load_module()
    sha = "b" * 40
    root = tmp_path / "evidence"
    attempt = ev.start_attempt(root, sha, "feature/y", 43)
    (attempt / "frontend.log").write_text("failed\n", encoding="utf-8")

    ev.finish_attempt(
        attempt,
        root / sha,
        sha,
        "feature/y",
        43,
        "failure",
        "frontend",
        1,
        False,
    )

    assert not (root / sha / "latest-success.json").exists()
    assert ev.verify_success(root / sha, sha) is False


def test_latest_attempt_e_restrito_a_attempts(tmp_path: Path):
    ev = _load_module()
    sha = "c" * 40
    root = tmp_path / "evidence"
    attempt = ev.start_attempt(root, sha, "feature/z", None)
    log = attempt / "backend.log"
    log.write_text("latest\n", encoding="utf-8")
    os.utime(log, None)

    found = ev.latest_log(root / sha, sha, 0)
    assert found == log.resolve()

    # Pointer manipulado tentando escapar da raiz deve falhar fechado.
    (root / sha / "latest-attempt.json").write_text(
        json.dumps({"target_sha": sha, "attempt": "../outside"}),
        encoding="utf-8",
    )
    assert ev.latest_log(root / sha, sha, 0) is None


def test_attempts_sao_unicos_mesmo_no_mesmo_segundo(tmp_path: Path):
    ev = _load_module()
    sha = "d" * 40
    root = tmp_path / "evidence"
    first = ev.start_attempt(root, sha, "feature/a", 1)
    second = ev.start_attempt(root, sha, "feature/a", 1)
    assert first != second
    assert first.parent == second.parent


def test_chave_do_app_exige_permissoes_owner_only(tmp_path: Path):
    if subprocess.run(["bash", "-n", str(AUTH_SCRIPT)], check=False).returncode != 0:
        pytest.fail("github-app-auth.sh possui sintaxe inválida")

    key = tmp_path / "app.pem"
    key.write_text("not-a-real-key\n", encoding="utf-8")
    key.chmod(0o644)
    cmd = (
        f"source {AUTH_SCRIPT!s}; "
        "EJC_FALLBACK_APP_PRIVATE_KEY_FILE=\"$1\"; "
        "_ejc_validate_private_key >/dev/null"
    )
    denied = subprocess.run(["bash", "-c", cmd, "_", str(key)], check=False)
    assert denied.returncode != 0

    key.chmod(0o600)
    allowed = subprocess.run(["bash", "-c", cmd, "_", str(key)], check=False)
    assert allowed.returncode == 0
