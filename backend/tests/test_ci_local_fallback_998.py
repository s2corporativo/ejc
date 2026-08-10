from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _block(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def test_componentes_do_fallback_tem_sintaxe_valida():
    bash_scripts = [
        "scripts/ci-local.sh",
        "scripts/ci-fallback.sh",
        "scripts/ci-fallback-watch.sh",
        "scripts/ci-fallback-activate.sh",
        "scripts/ci-worker-isolation.sh",
        "scripts/github-app-auth.sh",
        "scripts/governanca/ci-local-governanca.sh",
        "scripts/governanca/branch-protection.sh",
    ]
    for path in bash_scripts:
        proc = subprocess.run(
            ["bash", "-n", str(ROOT / path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"{path}: {proc.stderr}"

    proc = subprocess.run(
        ["python3", "-m", "py_compile", str(ROOT / "scripts/ci_evidence.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_control_plane_recusa_producao_e_exige_worker_isolado():
    source = _text("scripts/ci-fallback.sh")

    for marker in (
        "/opt/ejc/.deployed_sha",
        "/opt/ejc/.env",
        '"${APP_ENV:-}" != "production"',
        '"${EJC_ENV:-}" != "production"',
        '"$(id -u)" -ne 0',
        "assert_state_path",
        'ci-worker-isolation.sh" preflight',
    ):
        assert marker in source
    assert 'git merge-base --is-ancestor origin/main "$SHA"' in source
    assert '"$(git rev-parse FETCH_HEAD)" = "$SHA"' in source


def test_codigo_do_pr_nao_executa_diretamente_no_uid_controlador():
    source = _text("scripts/ci-fallback.sh")
    worker = _block(source, "run_worker_stage() {", "run_governance_stage() {")

    assert "ci-worker-isolation.sh" in worker
    assert "run-stage --sha" in worker
    assert '(cd "$WORKTREE"' not in source
    assert 'bash scripts/ci-local.sh backend' not in source
    assert 'bash scripts/ci-local.sh frontend' not in source


def test_runtime_do_worker_e_promovivel_sem_override_de_python():
    source = _text("scripts/ci-worker-isolation.sh")
    run = _block(source, "run_stage() {", 'case "$MODE" in')

    assert "env -i" in run
    assert "EJC_ALLOW_PYTHON_MISMATCH=0" in run
    assert "EJC_CI_STATE_ROOT" in run
    assert "EJC_CI_REPORT_ROOT" in run
    assert "EJC_FALLBACK_APP_PRIVATE_KEY_FILE" not in run[run.index("sudo -n -u") :]


def test_worker_tem_uid_home_processos_e_docker_separados():
    source = _text("scripts/ci-worker-isolation.sh")
    common = _block(source, "validate_common() {", "worker_runtime_preflight() {")

    assert "UID distinto do controlador" in common
    assert "grupo privilegiado" in common
    assert "Docker socket" in common
    assert "HOME cadastrado do worker é gravável" in common
    assert "chave privada do GitHub App" in common
    assert "configuração autenticada do gh" in common
    assert "worker possui sudo" in common

    cleanup = _block(source, "kill_worker_processes() {", "validate_common() {")
    assert "kill -KILL -1" in cleanup
    assert "/tmp /dev/shm" in cleanup
    assert "crontab -r" in cleanup


def test_cada_stage_recebe_snapshot_git_novo_e_trusted_ci():
    source = _text("scripts/ci-worker-isolation.sh")
    prepare = _block(source, "prepare_stage_source() {", "run_stage() {")

    assert "git clone" in prepare
    assert "--no-hardlinks" in prepare
    assert "--single-branch" in prepare
    assert 'rev-parse HEAD' in prepare
    assert "remote remove origin" in prepare
    assert ".ejc-ci-local-controller.sh" in prepare
    assert 'cp "$TRUST_ROOT/scripts/ci-local.sh"' in prepare
    assert "chmod 0555" in prepare


def test_full_gate_tem_identidade_de_app_sha_external_id_e_latest_run():
    source = _text("scripts/ci-fallback.sh")
    full_gate = _block(source, "full_gate_is_green() {", "publish_success_statuses() {")

    assert 'repos/$REPO/check-runs/$FULL_CHECK_ID' in full_gate
    assert ".head_sha == $sha" in full_gate
    assert ".external_id == $external_id" in full_gate
    assert ".app.id == $app_id" in full_gate
    assert '.status == "completed"' in full_gate
    assert '.conclusion == "success"' in full_gate
    assert "latest_full_check_id" in full_gate
    assert '[ "$latest" = "$FULL_CHECK_ID" ]' in full_gate


def test_latest_check_run_e_filtrado_no_servidor_por_nome_e_app():
    source = _text("scripts/ci-fallback.sh")
    block = _block(source, "latest_full_check_id() {", "full_gate_is_green() {")

    assert "--method GET" in block
    assert '-f check_name="$CONTEXT_FULL"' in block
    assert '-F app_id="$FALLBACK_APP_ID"' in block
    assert "filter=latest" in block


def test_sucesso_remoto_so_e_publicado_depois_dos_oito_gates():
    source = _text("scripts/ci-fallback.sh")
    final_publish = source.rindex("publish_success_statuses")
    markers = (
        "run_worker_stage backend",
        "run_worker_stage eval",
        "run_worker_stage frontend",
        "run_worker_stage p0",
        "run_governance_stage",
        "run_worker_stage architecture",
        "run_worker_stage continuity",
        "run_worker_stage ui-extra",
        'finish_attempt success "" 0 1',
        "revalidate_governance_for_merge",
    )
    for marker in markers:
        assert marker in source
        assert source.index(marker) < final_publish


def test_falha_de_worker_stage_nunca_publica_sucesso_parcial():
    source = _text("scripts/ci-fallback.sh")
    block = _block(source, "run_worker_stage() {", "run_governance_stage() {")

    assert "finish_attempt failure" in block
    assert 'post_status failure "$context"' in block
    assert "post_full_check failure" in block
    assert "post_status success" not in block
    assert "post_full_check success" not in block


def test_governanca_roda_script_trusted_contra_source_root():
    source = _text("scripts/ci-fallback.sh")
    block = _block(source, "run_governance() {", "revalidate_governance_for_merge() {")

    assert 'EJC_GOV_SOURCE_ROOT="$GOV_WORKTREE"' in block
    assert 'bash "$ROOT/scripts/governanca/ci-local-governanca.sh"' in block
    assert 'bash "$GOV_WORKTREE/scripts/governanca/ci-local-governanca.sh"' not in block


def test_merge_revalida_main_review_protecao_e_gate_duas_vezes():
    source = _text("scripts/ci-fallback.sh")
    snapshot = _block(source, "verify_merge_snapshot() {", "attempt_merge() {")
    merge = _block(source, "attempt_merge() {", "run_worker_stage() {")

    for marker in (
        "git fetch --quiet origin main",
        'git merge-base --is-ancestor origin/main "$SHA"',
        "local_evidence_is_green",
        "full_gate_is_green",
        "verify_branch_protection_for_merge",
        "reviewDecision",
        "APPROVED",
        "headRefOid",
        "retencao-humana",
    ):
        assert marker in snapshot

    assert merge.count("verify_merge_snapshot") >= 2
    assert 'repos/$REPO/pulls/$PR/merge' in merge
    assert '-f sha="$SHA"' in merge
    assert "migration potencialmente destrutiva" in merge


def test_branch_protection_e_conferida_antes_do_merge():
    source = _text("scripts/ci-fallback.sh")
    block = _block(source, "verify_branch_protection_for_merge() {", "verify_merge_snapshot() {")

    for marker in (
        ".required_status_checks.strict == true",
        "EJC Local Full Gate",
        ".enforce_admins.enabled == true",
        "required_approving_review_count",
        "require_code_owner_reviews",
        "require_last_push_approval",
        "required_conversation_resolution.enabled == true",
        "required_linear_history.enabled == true",
        "allow_force_pushes.enabled == false",
        "allow_deletions.enabled == false",
    ):
        assert marker in block


def test_promote_only_nunca_tenta_merge():
    source = _text("scripts/ci-fallback.sh")
    block = source[
        source.index('if [ "$PROMOTE_ONLY" -eq 1 ]') : source.index(
            'if [ "$MERGE_ONLY" -eq 1 ]'
        )
    ]
    assert "refresh_status_from_evidence" in block
    assert "attempt_merge" not in block


def test_ci_local_mantem_pg_loopback_e_sem_rm_rf():
    source = _text("scripts/ci-local.sh")
    assert '127.0.0.1:$PG_PORT:5432' in source
    assert '-p "$PG_PORT:5432"' not in source
    assert 's.bind(("127.0.0.1", 0))' in source
    assert "safe_remove_tree" in source
    assert "rm -rf" not in source


def test_ativador_valida_worker_antes_de_tocar_branch_protection():
    source = _text("scripts/ci-fallback-activate.sh")
    worker_preflight = source.index("ci-worker-isolation.sh\" preflight")
    protection = source.index("branch-protection.sh --fallback")
    install_watcher = source.index('install_watcher "$SCHEDULER"')

    assert worker_preflight < install_watcher < protection
    assert "EJC_CI_WORKER_USER" in source
    assert "EJC_CI_WORKER_ROOT" in source


def test_ativador_drena_e_restaura_protecao_antes_de_remover_produtor():
    source = _text("scripts/ci-fallback-activate.sh")
    disable = source[
        source.index('if [ "$MODE" = --disable ]') : source.index(
            '[ "$MODE" = --enable ]'
        )
    ]
    assert "create_drain" in disable
    assert "flock -w 120" in disable
    assert "branch-protection.sh --restore" in disable
    assert "remove_watcher" in disable
    assert disable.index("branch-protection.sh --restore") < disable.index("remove_watcher")
    assert 'rm -f "$DRAIN_FILE"' in disable
    assert "watcher preservado" in disable


def test_governanca_trata_worker_e_root_of_trust_como_sensivel():
    source = _text("scripts/governanca/ci-local-governanca.sh")

    assert "ci-worker-isolation" in source
    assert "ci_evidence" in source
    assert "github-app-auth" in source
    assert "security-auditor: executado" in source
    assert "git diff --name-only -z" in source
    assert "MIGRATION_RESERVATIONS.md" in source
