from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CI_LOCAL = ROOT / "scripts" / "ci-local.sh"


def _block(src: str, start: str, end: str) -> str:
    return src[src.index(start) : src.index(end)]


def test_backend_e_continuidade_encerram_seus_bancos_efemeros():
    src = CI_LOCAL.read_text(encoding="utf-8")
    backend = _block(src, "run_backend() {", "run_eval() {")
    continuity = _block(src, "run_continuity() {", "run_ui_extra() {")

    assert "ensure_venv" in backend
    assert "ensure_pip_audit" in backend
    assert "start_pg" in backend
    assert "stop_pg" in backend
    assert backend.index("ensure_venv") < backend.index("start_pg") < backend.index("stop_pg")

    assert "ensure_venv; start_pg" in continuity
    assert "stop_pg" in continuity
    assert continuity.index("start_pg") < continuity.index("stop_pg")


def test_stop_pg_reseta_estado_e_porta_dinamica_entre_estagios():
    src = CI_LOCAL.read_text(encoding="utf-8")
    stop = _block(src, "stop_pg() {", "_cleanup() {")

    assert 'PG_MODE=""' in stop
    assert 'PGBIN=""' in stop
    assert '[ -n "$PG_PORT_OVERRIDE" ] || PG_PORT=""' in stop

    assert 'PG_PORT_OVERRIDE="${PG_PORT:-}"' in src
    assert 'PG_PORT="$PG_PORT_OVERRIDE"' in src
    assert 's.bind(("127.0.0.1", 0))' in src


def test_postgres_local_exige_major_16_loopback_e_scram():
    src = CI_LOCAL.read_text(encoding="utf-8")
    start = _block(src, "start_pg() {", "run_backend() {")

    assert 'pg_major="$(' in start
    assert '[ "$pg_major" != "16" ]' in start
    assert 'EJC_ALLOW_POSTGRES_MISMATCH' in start
    assert "--auth-host=scram-sha-256" in start
    assert "--auth-local=trust" in start
    assert "listen_addresses=127.0.0.1" in start
    assert 'PGPASSWORD="$DBP"' in start


def test_postgres_docker_valida_major_real_16_antes_das_extensoes():
    src = CI_LOCAL.read_text(encoding="utf-8")
    start = _block(src, "start_pg() {", "run_backend() {")
    docker = start[start.index("PG_MODE=docker") : start.index("else\n    PG_MODE=local")]

    assert "SHOW server_version_num" in docker
    assert 'pg_docker_major="$((pg_version_num / 10000))"' in docker
    assert '[ "$pg_docker_major" = "16" ]' in docker
    assert "PostgreSQL Docker major" in docker
    assert docker.index("pg_isready") < docker.index("SHOW server_version_num")
    assert start.index("SHOW server_version_num") < start.index("CREATE EXTENSION IF NOT EXISTS vector")


def test_estado_mutavel_e_confinado_ao_state_root():
    src = CI_LOCAL.read_text(encoding="utf-8")

    assert "assert_state_root()" in src
    assert "assert_state_child()" in src
    assert 'assert_state_child "$PGDATA" "PGDATA"' in src
    assert 'assert_state_child "$REPORT_ROOT" "REPORT_ROOT"' in src
    assert 'assert_state_child "$REPORT_DIR" "REPORT_DIR"' in src
    assert '[ -z "$VENV_DIR_OVERRIDE" ] || assert_state_child "$VENV_DIR_OVERRIDE" "VENV_DIR"' in src
    assert 'assert_state_child "$RESTORE_DRILL_REPORT" "RESTORE_DRILL_REPORT"' in src
    assert "STATE_ROOT não pode ser symlink" in src
    assert "rm -rf" not in src


def test_full_executa_backend_antes_de_continuidade_com_ciclo_independente():
    src = CI_LOCAL.read_text(encoding="utf-8")
    case = src[src.index('case "$MODE" in') :]
    full_line = next(line for line in case.splitlines() if line.strip().startswith("full)"))

    assert "run_backend" in full_line
    assert "run_continuity" in full_line
    assert full_line.index("run_backend") < full_line.index("run_continuity")
    assert "run_backend; run_eval; run_frontend; run_p0; run_status; run_architecture; run_continuity" in full_line
