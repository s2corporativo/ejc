from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "scripts" / "ci-worker-isolation.sh"


def _text() -> str:
    return WORKER.read_text(encoding="utf-8")


def _block(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def test_preflight_sem_worker_falha_antes_de_tocar_host():
    env = os.environ.copy()
    env.pop("EJC_CI_WORKER_USER", None)
    proc = subprocess.run(
        ["bash", str(WORKER), "preflight"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "EJC_CI_WORKER_USER obrigatório" in (proc.stdout + proc.stderr)


def test_worker_e_uid_distinto_sem_grupos_privilegiados():
    source = _text()
    block = _block(source, "validate_common() {", "worker_runtime_preflight() {")
    assert 'worker_uid="$(id -u "$WORKER_USER")"' in block
    assert '[ "$worker_uid" -ne 0 ]' in block
    assert '[ "$worker_uid" -ne "$CONTROLLER_UID" ]' in block
    assert "docker|sudo|wheel|adm" in block
    assert "worker possui sudo não interativo" in block


def test_worker_nao_recebe_docker_socket_gh_chave_ou_evidencia():
    source = _text()
    common = _block(source, "validate_common() {", "worker_runtime_preflight() {")
    run = _block(source, "run_stage() {", 'case "$MODE" in')

    assert "/var/run/docker.sock" in common
    assert "worker consegue ler a chave privada do GitHub App" in common
    assert "worker consegue ler configuração autenticada do gh" in common
    assert "worker consegue ler evidência/estado do control plane" in common
    assert "worker consegue escrever evidência/estado do control plane" in common
    assert "worker consegue escrever no checkout do control plane" in common

    child_env = run[run.index("sudo -n -u") :]
    assert "GH_TOKEN=" not in child_env
    assert "GITHUB_TOKEN=" not in child_env
    assert "EJC_FALLBACK_APP_PRIVATE_KEY_FILE=" not in child_env
    assert "SSH_AUTH_SOCK=" not in child_env
    assert "/var/run/docker.sock" not in child_env


def test_worker_recebe_ambiente_minimo_e_git_safe_directory_exato():
    source = _text()
    run = _block(source, "run_stage() {", 'case "$MODE" in')
    assert "/usr/bin/env -i" in run
    for marker in (
        'HOME="$stage_root/home"',
        'TMPDIR="$stage_root/tmp"',
        'XDG_CACHE_HOME="$stage_root/state/cache"',
        'EJC_CI_STATE_ROOT="$stage_root/state"',
        'EJC_CI_REPORT_ROOT="$stage_root/state/reports"',
        "GIT_CONFIG_COUNT=1",
        "GIT_CONFIG_KEY_0=safe.directory",
        'GIT_CONFIG_VALUE_0="$source_dir"',
        "APP_ENV=development",
        "EJC_ENV=development",
        "EJC_ALLOW_PYTHON_MISMATCH=0",
        "CI=1",
    ):
        assert marker in run


def test_cada_stage_clona_sha_sem_hardlink_e_remove_origin():
    source = _text()
    prepare = _block(source, "prepare_stage_source() {", "run_stage() {")
    assert "git clone" in prepare
    assert "--no-hardlinks" in prepare
    assert "--single-branch" in prepare
    assert 'git -C "$source_dir" checkout --quiet --detach "$sha"' in prepare
    assert 'git -C "$source_dir" remote remove origin' in prepare
    assert '[ "$(git -C "$source_dir" rev-parse HEAD)" = "$sha" ]' in prepare


def test_orquestrador_trusted_nao_pode_ser_substituido_por_directory_write():
    source = _text()
    prepare = _block(source, "prepare_stage_source() {", "run_stage() {")
    run = _block(source, "run_stage() {", 'case "$MODE" in')
    assert 'cp "$TRUST_ROOT/scripts/ci-local.sh" "$trusted_ci"' in prepare
    assert 'chmod 0555 "$trusted_ci"' in prepare
    assert 'test ! -w "$source_dir"' in prepare
    assert 'test ! -w "$source_dir/scripts"' in prepare
    assert 'test ! -w "$trusted_ci"' in prepare
    assert 'setfacl -m "u:${WORKER_USER}:rx' in prepare
    assert 'bash "$trusted_ci" "$stage"' in run
    assert 'bash "$source_dir/scripts/ci-local.sh"' not in run


def test_worker_so_recebe_escrita_em_backend_frontend_e_estado_efemero():
    source = _text()
    prepare = _block(source, "prepare_stage_source() {", "run_stage() {")
    assert '"$source_dir/backend"' in prepare
    assert '"$source_dir/frontend"' in prepare
    assert '"$stage_root/home"' in prepare
    assert '"$stage_root/state"' in prepare
    assert '"$stage_root/tmp"' in prepare
    assert 'setfacl -Rm "u:${WORKER_USER}:rwX,u:${CONTROLLER_USER}:rwX" "$stage_root"' not in prepare


def test_worker_nao_pode_persistir_processos_cron_tmp_ou_home():
    source = _text()
    cleanup = _block(source, "kill_worker_processes() {", "validate_common() {")
    common = _block(source, "validate_common() {", "worker_runtime_preflight() {")
    assert "kill -KILL -1" in cleanup
    assert "/tmp /dev/shm" in cleanup
    assert "crontab -r" in cleanup
    assert "processo residual do worker permaneceu ativo" in cleanup
    assert "HOME cadastrado do worker é gravável" in common


def test_worker_exige_postgresql_16_e_extensoes_da_mesma_versao():
    source = _text()
    preflight = _block(source, "worker_runtime_preflight() {", "prepare_stage_source() {")
    assert 'PG_MAJOR_REQUIRED="${EJC_CI_PG_MAJOR_REQUIRED:-16}"' in source
    assert '[ "$PG_MAJOR_REQUIRED" = "16" ]' in preflight
    assert 'latest_pg_dir="$(ls -d /usr/lib/postgresql/*/bin' in preflight
    assert '[ "$latest_pg_dir" = "$PG_BIN_DIR" ]' in preflight
    for extension in ("vector", "pg_trgm", "pgcrypto"):
        assert extension in preflight
    assert "PostgreSQL 16 server não instalado" in preflight
    assert "psql_major" in preflight and '[ "$psql_major" = "16" ]' in preflight
    assert "pg_dump_major" in preflight and '[ "$pg_dump_major" = "16" ]' in preflight


def test_worker_rejeita_utilitario_at():
    source = _text()
    preflight = _block(source, "worker_runtime_preflight() {", "prepare_stage_source() {")
    assert "command -v at" in preflight


def test_stage_cleanup_e_fail_closed_apos_teste():
    source = _text()
    run = _block(source, "run_stage() {", 'case "$MODE" in')
    assert "cleanup_stage()" in run
    assert "kill_worker_processes" in run
    assert "clean_worker_persistence" in run
    assert 'safe_remove_tree "$stage_root"' in run
    last_return = run.rindex('return "$rc"')
    assert run.rindex("kill_worker_processes") < last_return
    assert run.rindex("clean_worker_persistence") < last_return
