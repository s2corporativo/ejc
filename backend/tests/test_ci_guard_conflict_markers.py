from __future__ import annotations

import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci_guard.sh"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def _repo_temporario(tmp_path: Path, conteudo: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _run(["git", "init", "-q"], repo).returncode == 0
    (repo / "arquivo.py").write_text(conteudo, encoding="utf-8")
    assert _run(["git", "add", "arquivo.py"], repo).returncode == 0
    return repo


def test_ci_guard_bloqueia_marcador_git_padrao(tmp_path: Path) -> None:
    repo = _repo_temporario(
        tmp_path,
        "<<<<<<< HEAD\nversao_a = 1\n=======\nversao_b = 2\n>>>>>>> feature\n",
    )

    resultado = _run(["bash", str(SCRIPT)], repo)

    assert resultado.returncode == 1
    assert "Marcadores de conflito encontrados" in resultado.stdout
    assert "Gate P0 falhou" in resultado.stdout


def test_ci_guard_bloqueia_separador_remanescente(tmp_path: Path) -> None:
    repo = _repo_temporario(tmp_path, "antes\n=======\ndepois\n")

    resultado = _run(["bash", str(SCRIPT)], repo)

    assert resultado.returncode == 1
    assert "Marcadores de conflito encontrados" in resultado.stdout


def test_ci_guard_bloqueia_marcador_diff3(tmp_path: Path) -> None:
    repo = _repo_temporario(tmp_path, "||||||| base\nvalor = 1\n")

    resultado = _run(["bash", str(SCRIPT)], repo)

    assert resultado.returncode == 1
    assert "Marcadores de conflito encontrados" in resultado.stdout


def test_ci_guard_nao_confunde_separador_decorativo(tmp_path: Path) -> None:
    repo = _repo_temporario(tmp_path, "================================\nvalor = 1\n")

    resultado = _run(["bash", str(SCRIPT)], repo)

    assert resultado.returncode == 0
    assert "Gate P0 aprovado" in resultado.stdout


def test_ci_guard_aprova_arquivo_sem_conflito(tmp_path: Path) -> None:
    repo = _repo_temporario(tmp_path, "valor = 1\n")

    resultado = _run(["bash", str(SCRIPT)], repo)

    assert resultado.returncode == 0
    assert "Gate P0 aprovado" in resultado.stdout
