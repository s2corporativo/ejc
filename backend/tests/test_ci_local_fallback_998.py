from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _block(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def test_scripts_fallback_tem_sintaxe_valida():
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


def test_control_plane_recusa_producao_root_runtime_divergente_e_sha_stale():
    src = _text("scripts/ci-fallback.sh")
    assert "/opt/ejc" in src
    assert '"${APP_ENV:-}" != "production"' in src
    assert '"${EJC_ENV:-}" != "production"' in src
    assert '"$(id -u)" -ne 0' in src
    assert 'git merge-base --is-ancestor origin/main "$SHA"' in src
    assert '"$(git rev-parse FETCH_HEAD)" = "$SHA"' in src
    assert "EJC_ALLOW_PYTHON_MISMATCH=1 é somente diagnóstico" in src
    assert "ci-worker-isolation.sh" in src
    assert "worker isolado não atende aos invariantes" in src
    assert "Docker é obrigatório para fallback promovível" not in src


def test_codigo_do_pr_e_delegado_ao_worker_e_governanca_e_trusted():
    src = _text("scripts/ci-fallback.sh")
    worker = _block(src, "run_worker_stage() {", "run_governance_stage() {")
    governance = _block(src, "run_governance() {", "revalidate_governance_for_merge() {")

    assert 'ci-worker-isolation.sh" run-stage --sha "$SHA" --stage "$key"' in worker
    assert 'EJC_CI_STATE_ROOT="$STATE_ROOT"' in worker
    assert 'EJC_GOV_SOURCE_ROOT="$GOV_WORKTREE"' in governance
    assert 'bash "$ROOT/scripts/governanca/ci-local-governanca.sh"' in governance
    assert "bash scripts/ci-local.sh backend" not in src
    assert "bash scripts/ci-local.sh frontend" not in src


def test_full_gate_exige_id_sha_app_external_id_e_latest_check_run():
    src = _text("scripts/ci-fallback.sh")
    gate = _block(src, "full_gate_is_green() {", "publish_success_statuses() {")

    assert 'check-runs/$FULL_CHECK_ID' in gate
    assert '.head_sha == $sha' in gate
    assert '.external_id == $external_id' in gate
    assert '.app.id == $app_id' in gate
    assert '.status == "completed"' in gate
    assert '.conclusion == "success"' in gate
    assert "latest_full_check_id" in gate
    assert '[ "$latest" = "$FULL_CHECK_ID" ]' in gate


def test_sucesso_remoto_so_e_publicado_depois_dos_oito_gates():
    src = _text("scripts/ci-fallback.sh")
    pos_finish = src.index('finish_attempt success "" 0 1')
    pos_publish = src.rindex("publish_success_statuses")
    for marker in (
        "run_worker_stage backend",
        "run_worker_stage eval",
        "run_worker_stage frontend",
        "run_worker_stage p0",
        "run_governance_stage",
        "run_worker_stage architecture",
        "run_worker_stage continuity",
        "run_worker_stage ui-extra",
    ):
        assert marker in src
        assert src.index(marker) < pos_finish < pos_publish


def test_falha_de_stage_registra_failure_sem_success_parcial():
    src = _text("scripts/ci-fallback.sh")
    block = _block(src, "run_worker_stage() {", "run_governance_stage() {")
    assert "finish_attempt failure" in block
    assert 'post_status failure "$context"' in block
    assert "post_full_check failure" in block
    assert "post_status success" not in block
    assert "post_full_check success" not in block


def test_merge_revalida_evidencia_main_review_protecao_gate_e_sha_duas_vezes():
    src = _text("scripts/ci-fallback.sh")
    snapshot = _block(src, "verify_merge_snapshot() {", "attempt_merge() {")
    merge = _block(src, "attempt_merge() {", "run_worker_stage() {")

    assert "git fetch --quiet origin main" in snapshot
    assert 'git merge-base --is-ancestor origin/main "$SHA"' in snapshot
    assert "local_evidence_is_green" in snapshot
    assert "full_gate_is_green" in snapshot
    assert "verify_branch_protection_for_merge" in snapshot
    assert '[ "$review_decision" = "APPROVED" ]' in snapshot
    assert "headRefOid" in snapshot
    assert "retencao-humana" in snapshot
    assert merge.count("verify_merge_snapshot") >= 2
    assert "migration com patch indisponível/truncado" in merge
    assert "migration potencialmente destrutiva" in merge
    assert 'repos/$REPO/pulls/$PR/merge' in merge
    assert '-f sha="$SHA"' in merge


def test_branch_protection_live_e_conferida_antes_do_merge():
    src = _text("scripts/ci-fallback.sh")
    block = _block(src, "verify_branch_protection_for_merge() {", "verify_merge_snapshot() {")
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


def test_ci_local_mantem_pg_loopback_scram_estado_confinado_e_tooling_separado():
    src = _text("scripts/ci-local.sh")
    assert '127.0.0.1:$PG_PORT:5432' in src
    assert '-p "$PG_PORT:5432"' not in src
    assert 's.bind(("127.0.0.1", 0))' in src
    assert "--auth-host=scram-sha-256" in src
    assert 'listen_addresses=127.0.0.1' in src
    assert "assert_state_root" in src
    assert 'assert_state_child "$PGDATA" "PGDATA"' in src
    assert 'assert_state_child "$REPORT_DIR" "REPORT_DIR"' in src
    assert 'tool_dir="$STATE_ROOT/tools/pip-audit-' in src
    assert 'PIP_AUDIT_BIN="$tool_dir/bin/pip-audit"' in src
    assert "rm -rf" not in src


def test_watcher_preserva_retencao_incremental_e_classifica_falha_pre_stage():
    src = _text("scripts/ci-fallback-watch.sh")
    for marker in (
        "local_evidence_green",
        "--merge-only",
        "--promote-only",
        "GREEN_RECHECK_SECONDS",
        "pr_state_due",
        "ci_evidence.py\" prune",
        "EVIDENCE_MAX_SHAS",
        "failure_is_infrastructure",
        "invocation_log",
        "latest_attempt_log",
        "GitHub/fetch indisponível",
        "git merge --ff-only origin/main",
    ):
        assert marker in src
    assert "git reset --hard" not in src
    assert "git push --force" not in src


def test_ativacao_valida_worker_antes_da_protecao_e_disable_restaura_antes_de_remover_produtor():
    src = _text("scripts/ci-fallback-activate.sh")
    pos_worker = src.index("ci-worker-isolation.sh\" preflight")
    pos_fallback = src.index("branch-protection.sh --fallback")
    assert pos_worker < pos_fallback
    assert "create_drain" in src
    assert "install_watcher \"$SCHEDULER\"" in src
    assert src.index("install_watcher \"$SCHEDULER\"") < pos_fallback

    disable = src[src.index('if [ "$MODE" = --disable ]') : src.index('[ "$MODE" = --enable ]')]
    assert "flock -w 120 8" in disable
    assert disable.index("branch-protection.sh --restore") < disable.index("remove_watcher")
    assert "watcher preservado e reativado" in disable
    assert "branch-protection.sh --cloud" not in disable


def test_branch_protection_modifica_somente_required_status_checks():
    src = _text("scripts/governanca/branch-protection.sh")
    executable = src.split("cat <<'FIM'", 1)[0]
    assert "protection/required_status_checks" in executable
    assert 'gh api -X PATCH "$API"' in executable
    assert "-X PUT" not in executable
    assert "EJC Local Full Gate" in executable
    assert "app_id" in executable
    assert "required_pull_request_reviews" not in executable
    assert "restrictions" not in executable


def test_governanca_local_e_trusted_nul_safe_e_cobre_root_of_trust():
    src = _text("scripts/governanca/ci-local-governanca.sh")
    assert "EJC_GOV_SOURCE_ROOT" in src
    assert "git diff --name-only -z" in src
    assert "read -r -d ''" in src
    assert 'grep -EIn "$PADROES" -- "$f"' in src
    assert "ci-worker-isolation" in src
    assert "ci_evidence" in src
    assert "github-app-auth" in src
    assert "github_pat_" in src
    assert "security-auditor: executado" in src
    assert "MIGRATION_RESERVATIONS.md" in src


def test_ci_local_cobre_paridade_minima_dos_gates_atuais():
    src = _text("scripts/ci-local.sh")
    required = [
        '"$PY" -m ruff check',
        "pip-audit==2.10.0",
        "--cov-fail-under=65",
        "app.eval.run_eval --smoke",
        "app.eval.agent_trajectory",
        "npm run format:check",
        "npm run test -- --reporter=dot",
        "npm audit --audit-level=high",
        "scripts/ci_guard.sh",
        "test_backup_wrapper.sh",
        "test_deploy_rollback.sh",
        "test_selfhosted_runner_setup.sh",
        "test_generate_architecture_inventory",
        "restore_drill.py",
        "npm run lint:eslint",
        "playwright install chromium",
        "npm run test:responsive",
        "npm run test:premium-responsive",
    ]
    for marker in required:
        assert marker in src, marker
