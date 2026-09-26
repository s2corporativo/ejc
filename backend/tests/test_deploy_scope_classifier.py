from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "classify_deploy_scope.py"


def _module():
    spec = importlib.util.spec_from_file_location("classify_deploy_scope", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, path: str, content: str, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=EJC Test", "-c",
         "user.email=e2e@example.invalid", "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def test_frontend_only_quando_todo_diff_esta_no_frontend(tmp_path: Path):
    mod = _module()
    _git(tmp_path, "init", "-q")
    base = _commit(tmp_path, "frontend/src/App.tsx", "a", "base")
    target = _commit(tmp_path, "frontend/src/App.tsx", "b", "ui")
    assert mod.classify(tmp_path, base, target) == "frontend"


def test_backend_forca_full(tmp_path: Path):
    mod = _module()
    _git(tmp_path, "init", "-q")
    base = _commit(tmp_path, "frontend/src/App.tsx", "a", "base")
    target = _commit(tmp_path, "backend/app/main.py", "x", "backend")
    assert mod.classify(tmp_path, base, target) == "full"


def test_diff_misto_forca_full(tmp_path: Path):
    mod = _module()
    _git(tmp_path, "init", "-q")
    base = _commit(tmp_path, "frontend/src/App.tsx", "a", "base")
    (tmp_path / "frontend/src/App.tsx").write_text("b", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/x.sh").write_text("echo x", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "user.name=EJC Test", "-c",
         "user.email=e2e@example.invalid", "commit", "-m", "mixed")
    target = _git(tmp_path, "rev-parse", "HEAD")
    assert mod.classify(tmp_path, base, target) == "full"


def test_sha_invalido_e_historico_desconhecido_falham_fechado(tmp_path: Path):
    mod = _module()
    _git(tmp_path, "init", "-q")
    base = _commit(tmp_path, "frontend/src/App.tsx", "a", "base")
    assert mod.classify(tmp_path, "nao-e-sha", base) == "full"
    assert mod.classify(tmp_path, "0" * 40, base) == "full"
