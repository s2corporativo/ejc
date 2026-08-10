from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
CI_LOCAL = ROOT / "scripts" / "ci-local.sh"


def _text() -> str:
    return CI_LOCAL.read_text(encoding="utf-8")


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
    assert "STATE_ROOT inseguro" in (proc.stdout + proc.stderr)


def test_venv_da_aplicacao_e_content_addressed_lockado_e_promovido_atomicamente():
    source = _text()
    resolve = _block(source, "resolve_venv_dir() {", "ensure_venv() {")
    ensure = _block(source, "ensure_venv() {", "ensure_pip_audit() {")

    assert "requirements.txt" in resolve
    assert "sha256" in resolve
    assert "python_runtime_key" in resolve
    assert ".ejc-ready" in ensure
    assert "flock" in ensure
    assert ".build.$$.$RANDOM" in ensure
    assert '-m pip check' in ensure
    assert 'mv "$build_dir" "$VENV_DIR"' in ensure
    assert "CI_SKIP_PIP=1 solicitado" in ensure


def test_pip_audit_vive_em_tool_venv_separado_e_nao_muta_app_venv():
    source = _text()
    audit = _block(source, "ensure_pip_audit() {", "check_node() {")
    backend = _block(source, "run_backend() {", "run_eval() {")

    assert 'tool_dir="$STATE_ROOT/tools/pip-audit-' in audit
    assert 'pip-audit==$PIP_AUDIT_VERSION' in audit
    assert 'PIP_AUDIT_BIN="$tool_dir/bin/pip-audit"' in audit
    assert '"$PIP_AUDIT_BIN" -r requirements.txt --desc' in backend
    assert '"$VENV_DIR/bin/pip-audit"' not in source
    assert '"$PY" -m pip install' not in backend


def test_postgres_local_e_loopback_scram_e_major_16_fail_closed():
    source = _text()
    pg = _block(source, "start_pg() {", "run_backend() {")

    assert 'listen_addresses=127.0.0.1' in pg
    assert "--auth-host=scram-sha-256" in pg
    assert '"$pg_major" != "16"' in pg
    assert "EJC_ALLOW_POSTGRES_MISMATCH" in pg
    assert "CREATE EXTENSION IF NOT EXISTS vector" in pg
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in pg
    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in pg


def test_estado_relatorios_restore_e_pgdata_ficam_sob_state_root():
    source = _text()
    for marker in (
        'assert_state_child "$PGDATA" "PGDATA"',
        'assert_state_child "$REPORT_ROOT" "REPORT_ROOT"',
        'assert_state_child "$REPORT_DIR" "REPORT_DIR"',
        'assert_state_child "$RESTORE_DRILL_REPORT" "RESTORE_DRILL_REPORT"',
    ):
        assert marker in source
    assert 'find "$path" -depth -mindepth 1 -delete' in source
    assert "rm -rf" not in source


def test_stage_browser_nao_instala_dependencias_de_so_com_privilegio():
    source = _text()
    ui = _block(source, "run_ui_extra() {", "run_fast() {")
    assert "playwright install chromium" in ui
    assert "--with-deps" not in ui
    assert "sudo" not in ui
    assert "apt-get" not in ui
