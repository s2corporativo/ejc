"""O guard deve reprovar novas cópias sem imprimir seu conteúdo."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check_redundancias.py"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def test_guard_detecta_copia_nova_e_preserva_baseline(tmp_path):
    assert SCRIPT.exists(), "Falta o guard local de redundâncias"
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "ficticio@example.invalid")
    git(tmp_path, "config", "user.name", "Teste fictício")
    source = tmp_path / "backend/app"
    source.mkdir(parents=True)
    block = "\n".join(f"resultado_{i} = calcular({i}, 'massa ficticia')" for i in range(18)) + "\n"
    (source / "um.py").write_text(block)
    (source / "dois.py").write_text(block)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "baseline fictícia")
    base = git(tmp_path, "rev-parse", "HEAD")

    def run():
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--base-ref", base],
            capture_output=True, text=True,
        )

    assert run().returncode == 0  # dívida preexistente permanece explícita
    (source / "tres.py").write_text("# Comentário diferente\n" + block)
    result = run()
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["new_groups"] > 0
    assert any(o["path"] == "backend/app/tres.py" for g in report["findings"] for o in g["occurrences"])
    assert "massa ficticia" not in result.stdout
    (source / "tres.py").write_text("from .um import resultado_0\n")
    assert run().returncode == 0
    invalid = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--base-ref", "referencia-inexistente"],
        capture_output=True, text=True,
    )
    assert invalid.returncode == 2  # referência ausente nunca produz falso verde


def test_guard_cobre_css_ts_e_repeticao_no_mesmo_arquivo(tmp_path):
    assert SCRIPT.exists(), "Falta o guard local de redundâncias"
    spec = importlib.util.spec_from_file_location("guard_redundancias", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for suffix in (".css", ".tsx", ".sh"):
        block = "\n".join(f"  campo{i}: valor{i};" for i in range(18))
        path = f"frontend/src/exemplo{suffix}"
        groups = module.groups({path: block + "\n\n" + block})
        assert groups and any(len(occurrences) == 2 for occurrences in groups.values())
