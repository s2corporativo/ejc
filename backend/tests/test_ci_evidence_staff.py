from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import subprocess
import time
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


def test_prune_remove_sha_antigo_mas_preserva_sha_travado(tmp_path: Path):
    ev = _load_module()
    root = tmp_path / "evidence"
    old_sha = "e" * 40
    locked_sha = "f" * 40
    recent_sha = "1" * 40

    for sha in (old_sha, locked_sha, recent_sha):
        attempt = ev.start_attempt(root, sha, "feature/prune", 1)
        (attempt / "backend.log").write_text("ok\n", encoding="utf-8")
        ev.finish_attempt(
            attempt,
            root / sha,
            sha,
            "feature/prune",
            1,
            "success",
            None,
            0,
            True,
        )

    old_time = time.time() - 60 * 86400
    for sha in (old_sha, locked_sha):
        for path in (root / sha).rglob("*"):
            if not path.is_symlink():
                os.utime(path, (old_time, old_time), follow_symlinks=False)
        os.utime(root / sha, (old_time, old_time))

    lock_path = root / locked_sha / ".lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        stats = ev.prune_evidence(root, max_shas=1, max_age_days=30, attempts_per_sha=1)
        assert stats["removed_shas"] == 1
        assert stats["skipped_locked"] == 1
        assert not (root / old_sha).exists()
        assert (root / locked_sha).exists()
        assert (root / recent_sha).exists()


def test_prune_quarentena_nao_remove_namespace_recriado_do_mesmo_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ev = _load_module()
    root = tmp_path / "evidence"
    old_sha = "3" * 40
    recent_sha = "4" * 40

    for sha in (old_sha, recent_sha):
        attempt = ev.start_attempt(root, sha, "feature/race", 1)
        (attempt / "backend.log").write_text("ok\n", encoding="utf-8")
        ev.finish_attempt(
            attempt,
            root / sha,
            sha,
            "feature/race",
            1,
            "success",
            None,
            0,
            True,
        )

    old_time = time.time() - 60 * 86400
    for path in (root / old_sha).rglob("*"):
        if not path.is_symlink():
            os.utime(path, (old_time, old_time), follow_symlinks=False)
    os.utime(root / old_sha, (old_time, old_time))

    original_remove = ev._remove_tree_no_follow
    recreated = False

    def recreate_then_remove(path: Path) -> None:
        nonlocal recreated
        if path.name.startswith(f".prune-{old_sha}-") and not recreated:
            recreated = True
            new_attempt = ev.start_attempt(root, old_sha, "feature/new", 2)
            (new_attempt / "backend.log").write_text("new\n", encoding="utf-8")
        original_remove(path)

    monkeypatch.setattr(ev, "_remove_tree_no_follow", recreate_then_remove)
    stats = ev.prune_evidence(root, max_shas=1, max_age_days=30, attempts_per_sha=1)

    assert recreated is True
    assert stats["removed_shas"] == 1
    assert (root / old_sha).is_dir()
    assert (root / old_sha / "latest-attempt.json").is_file()
    assert not list(root.glob(f".prune-{old_sha}-*"))


def test_prune_preserva_attempt_referenciado_por_latest_success(tmp_path: Path):
    ev = _load_module()
    sha = "2" * 40
    root = tmp_path / "evidence"
    success = ev.start_attempt(root, sha, "feature/keep", 1)
    (success / "backend.log").write_text("ok\n", encoding="utf-8")
    ev.finish_attempt(
        success,
        root / sha,
        sha,
        "feature/keep",
        1,
        "success",
        None,
        0,
        True,
    )

    stale = ev.start_attempt(root, sha, "feature/keep", 1)
    (stale / "backend.log").write_text("failed\n", encoding="utf-8")
    ev.finish_attempt(
        stale,
        root / sha,
        sha,
        "feature/keep",
        1,
        "failure",
        "backend",
        1,
        False,
    )

    old_time = time.time() - 60 * 86400
    os.utime(success, (old_time, old_time))
    os.utime(stale, (old_time, old_time))
    ev.prune_evidence(root, max_shas=10, max_age_days=30, attempts_per_sha=1)

    assert success.exists()
    assert ev.verify_success(root / sha, sha) is True


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
