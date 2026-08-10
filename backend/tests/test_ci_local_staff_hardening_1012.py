from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
CI_LOCAL = ROOT / "scripts" / "ci-local.sh"


def _block(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def test_state_root_apontando_para_checkout_falha_antes_de_executar_gate():
    env = os.environ.copy()
    env.update(
        {
            "EJC_ALLOW_ROOT_DIAGNOSTIC": "1",
            "EJC_CI_STATE_ROOT": str(ROOT),
            "APP_ENV": "development",
            "EJC_ENV": "development",
        }
    )
    proc = subprocess.run(
        ["bash", str(CI_LOCAL), "fast"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    assert "STATE_ROOT deve ficar fora do checkout" in (proc.stdout + proc.stderr)


def test_pip_audit_nao_muta_venv_da_aplicacao():
    source = CI_LOCAL.read_text(encoding="utf-8")
    backend = _block(source, "run_backend() {", "run_eval() {")
    audit = _block(source, "ensure_pip_audit() {", "check_node() {")

    assert "ensure_pip_audit" in backend
    assert '"$PIP_AUDIT_BIN" -r requirements.txt --desc' in backend
    assert '"$PY" -m pip install' not in backend
    assert '"$VENV_DIR/bin/pip-audit"' not in source
    assert 'pip-audit==${PIP_AUDIT_VERSION}' in audit
    assert 'tool_dir="$TOOLS_ROOT/pip-audit-' in audit


def test_venv_aplicacao_usa_lock_ready_marker_e_pip_check():
    source = CI_LOCAL.read_text(encoding="utf-8")
    ensure = _block(source, "ensure_venv() {", "ensure_pip_audit() {")

    assert '.ejc-ready' in ensure
    assert 'flock 7' in ensure
    assert 'CI_FORCE_PIP' in ensure
    assert '-m pip check' in ensure
    assert 'CI_SKIP_PIP=1 solicitado' in ensure


def test_paths_de_artefato_e_banco_sao_limitados_ao_state_root():
    source = CI_LOCAL.read_text(encoding="utf-8")

    for variable in ("PGDATA", "REPORT_ROOT", "REPORT_DIR", "TOOLS_ROOT"):
        assert f'assert_under_state "${variable}"' in source
    assert 'assert_under_state "$RESTORE_DRILL_REPORT"' in source


def test_full_reutiliza_build_ja_validado_sem_perder_build_standalone():
    source = CI_LOCAL.read_text(encoding="utf-8")
    frontend = _block(source, "run_frontend() {", "run_p0() {")
    ui = _block(source, "run_ui_extra() {", "run_fast() {")

    assert 'FRONTEND_BUILD_VALIDATED=1' in frontend
    assert 'if [ "$FRONTEND_BUILD_VALIDATED" -eq 0 ]' in ui
    assert "npm run build" in ui
    full_line = next(
        line
        for line in source[source.index('case "$MODE" in') :].splitlines()
        if line.strip().startswith("full)")
    )
    assert full_line.index("run_frontend") < full_line.index("run_ui_extra")
