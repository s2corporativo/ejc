from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CI_LOCAL = ROOT / "scripts" / "ci-local.sh"


def test_venv_e_identificado_por_python_e_requirements_hash():
    src = CI_LOCAL.read_text(encoding="utf-8")

    assert 'VENV_DIR_OVERRIDE="${VENV_DIR:-}"' in src
    assert 'hashlib.sha256(pathlib.Path("backend/requirements.txt").read_bytes())' in src
    assert 'py_version="$($PYTHON_BIN -c' in src
    assert 'VENV_DIR="$STATE_ROOT/venv-py${py_key}-${req_hash}"' in src


def test_skip_pip_nao_cria_venv_vazio_e_finge_reuso():
    src = CI_LOCAL.read_text(encoding="utf-8")
    ensure = src[src.index("ensure_venv() {") : src.index("check_node() {")]

    assert 'CI_SKIP_PIP:-0}" = "1"' in ensure
    assert 'venv hermético não existe' in ensure
    assert ensure.index("CI_SKIP_PIP=1 solicitado") < ensure.index('"$PYTHON_BIN" -m venv')


def test_mudanca_de_requirements_separa_ambiente_python():
    src = CI_LOCAL.read_text(encoding="utf-8")

    # Não é permitido voltar ao diretório fixo que poderia conservar pacote
    # removido de uma versão anterior dos requirements.
    assert 'VENV_DIR="${VENV_DIR:-$STATE_ROOT/venv-py311}"' not in src
    assert "resolve_venv_dir" in src
