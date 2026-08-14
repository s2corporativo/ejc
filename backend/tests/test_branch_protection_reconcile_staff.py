from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "governanca" / "branch-protection.sh"


def _fake_gh(tmp_path: Path, *, matching_get: bool) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    if matching_get:
        get_payload = r'''{"strict":true,"checks":[{"context":"Backend — suíte completa + schema/RAG (Postgres pgvector)","app_id":null},{"context":"Eval — smoke dos gold sets (offline, bloqueante)","app_id":null},{"context":"Frontend — testes + typecheck + build","app_id":null},{"context":"P0 guard — conflitos e segredos","app_id":null},{"context":"Governança — travas de PR","app_id":null}]}'''
    else:
        get_payload = r'''{"strict":true,"checks":[{"context":"OUTRO CHECK","app_id":null}]}'''

    gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [ \"${1:-}\" = auth ] && [ \"${2:-}\" = status ]; then exit 0; fi\n"
        "if [ \"${1:-}\" = api ]; then\n"
        "  shift\n"
        "  if [ \"${1:-}\" = -X ] && [ \"${2:-}\" = PATCH ]; then\n"
        "    cat >/dev/null\n"
        "    exit 1\n"
        "  fi\n"
        f"  printf '%s\\n' '{get_payload}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 2\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    return bin_dir


def _run(tmp_path: Path, *, matching_get: bool) -> subprocess.CompletedProcess[str]:
    if shutil.which("jq") is None:
        pytest.skip("jq ausente no host de testes")
    bin_dir = _fake_gh(tmp_path, matching_get=matching_get)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(SCRIPT), "--cloud"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_patch_sem_resposta_mas_estado_aplicado_e_confirmado(tmp_path: Path):
    result = _run(tmp_path, matching_get=True)
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "estado solicitado confirmado por read-after-write" in combined
    assert "demais proteções não foram tocadas" in combined


def test_patch_sem_resposta_e_estado_divergente_falha_fechado(tmp_path: Path):
    result = _run(tmp_path, matching_get=False)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "estado efetivo não corresponde ao payload solicitado" in combined
    assert "não foi possível aplicar/reconciliar" in combined
