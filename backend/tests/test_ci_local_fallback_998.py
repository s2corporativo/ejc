from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_scripts_fallback_tem_sintaxe_valida():
    bash_scripts = [
        "scripts/ci-local.sh",
        "scripts/ci-fallback.sh",
        "scripts/ci-fallback-watch.sh",
        "scripts/ci-fallback-activate.sh",
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


def test_fallback_recusa_producao_root_runtime_divergente_e_sha_stale():
    src = _text("scripts/ci-fallback.sh")
    assert "/opt/ejc" in src
    assert '"${APP_ENV:-}" != "production"' in src
    assert '"${EJC_ENV:-}" != "production"' in src
    assert '"$(id -u)" -ne 0' in src
    assert "ejc_worker" in src
    assert 'git merge-base --is-ancestor origin/main "$SHA"' in src
    assert 'git worktree add --detach "$WORKTREE" "$SHA"' in src
    assert '"$(git rev-parse FETCH_HEAD)" = "$SHA"' in src
    assert "Docker é obrigatório para fallback promovível" in src


def test_status_promovivel_exige_runtime_canonico_e_app_renovavel():
    src = _text("scripts/ci-fallback.sh")
    assert 'EJC_ALLOW_PYTHON_MISMATCH:-0}" = "1"' in src
    assert "não pode publicar gate promovível" in src
    assert "EJC_ALLOW_PYTHON_MISMATCH=0 bash scripts/ci-local.sh backend" in src
    assert "EJC_ALLOW_PYTHON_MISMATCH=0 bash scripts/ci-local.sh eval" in src
    assert "EJC_ALLOW_PYTHON_MISMATCH=0 bash scripts/ci-local.sh continuity" in src
    assert "EJC_FALLBACK_INSTALLATION_ID" in src
    assert "EJC_FALLBACK_APP_PRIVATE_KEY_FILE" in src
    assert "source \"$ROOT/scripts/github-app-auth.sh\"" in src


def test_ci_local_recusa_host_produtivo_e_contem_estado_mutavel():
    src = _text("scripts/ci-local.sh")
    assert "/opt/ejc/.deployed_sha" in src
    assert "/opt/ejc/.env" in src
    for name in ("ejc_backend", "ejc_worker", "ejc_db", "ejc_frontend", "ejc_redis"):
        assert name in src
    assert '127.0.0.1:$PG_PORT:5432' in src
    assert '-p "$PG_PORT:5432"' not in src
    assert 's.bind(("127.0.0.1", 0))' in src
    assert "assert_state_root" in src
    assert 'assert_state_child "$PGDATA" "PGDATA"' in src
    assert 'assert_state_child "$REPORT_DIR" "REPORT_DIR"' in src
    assert "STATE_ROOT não pode ser symlink" in src
    assert "rm -rf" not in src


def test_postgresql_promovivel_e_16_loopback_e_scram():
    src = _text("scripts/ci-local.sh")
    assert "PostgreSQL local major $pg_major detectado; o CI canônico exige 16" in src
    assert "--auth-host=scram-sha-256" in src
    assert "--auth-local=trust" in src
    assert 'listen_addresses=127.0.0.1' in src
    assert 'PGPASSWORD="$DBP"' in src


def test_ci_local_pina_auditoria_e_prepara_schema_no_restore_drill():
    src = _text("scripts/ci-local.sh")
    assert "pip-audit==2.10.0" in src
    continuity = src[src.index("run_continuity() {") : src.index("run_ui_extra() {")]
    assert '"$PY" -m alembic upgrade head' in continuity
    assert "restore_drill.py" in continuity
    assert continuity.index("alembic upgrade head") < continuity.index("restore_drill.py")
    assert 'assert_state_child "$RESTORE_DRILL_REPORT"' in continuity


def test_browser_local_nao_instala_dependencias_privilegiadas_do_so():
    src = _text("scripts/ci-local.sh")
    ui = src[src.index("run_ui_extra() {") : src.index("run_fast() {")]
    assert "playwright install chromium" in ui
    assert "--with-deps" not in ui
    assert "sudo" not in ui
    assert "apt-get" not in ui


def test_full_gate_so_e_publicado_apos_todos_os_gates_e_governanca_atual():
    src = _text("scripts/ci-fallback.sh")
    pos_publish = src.rindex("publish_success_statuses")
    for marker in (
        "run_stage backend",
        "run_stage eval",
        "run_stage frontend",
        "run_stage p0",
        "run_stage governanca",
        "run_stage architecture",
        "run_stage continuity",
        "run_stage ui-extra",
        "revalidate_governance_for_merge",
    ):
        assert marker in src
        assert src.index(marker) < pos_publish


def test_falha_de_stage_registra_evidencia_e_failure_sem_success_parcial():
    src = _text("scripts/ci-fallback.sh")
    block = src[src.index("run_stage() {") : src.index("run_stage backend ")]
    assert "finish_attempt failure" in block
    assert 'post_status failure "$context"' in block
    assert "post_full_check failure" in block
    assert "post_status success" not in block


def test_preflight_app_acontece_antes_da_suite_e_valida_app_e_sha():
    src = _text("scripts/ci-fallback.sh")
    assert "preflight_app_credential()" in src
    assert "GitHub App não conseguiu criar Check Run" in src
    assert 'app_id" = "$FALLBACK_APP_ID"' in src
    assert 'head_sha" = "$SHA"' in src
    assert src.index("preflight_app_credential\n") < src.index("run_stage backend ")


def test_cleanup_global_cobre_worktrees_e_token_efemero():
    src = _text("scripts/ci-fallback.sh")
    cleanup = src[src.index("cleanup_worktrees() {") : src.index("preflight_app_credential() {")]
    assert "GOV_WORKTREE" in cleanup
    assert "WORKTREE" in cleanup
    assert "git worktree remove --force" in cleanup
    assert "ejc_github_app_clear" in cleanup
    assert "trap cleanup_worktrees EXIT" in src


def test_status_remoto_indisponivel_preserva_prova_local_mas_nao_promove():
    src = _text("scripts/ci-fallback.sh")
    post = src[src.index("post_status() {") : src.index("publish_success_statuses() {")]
    assert "STATUS_SYNC_PENDING=1" in post
    assert "evidência local preservada" in post
    assert "return 75" in post
    assert "full_gate_is_green" in src


def test_evidencia_e_content_addressed_e_attempt_scoped():
    src = _text("scripts/ci-fallback.sh")
    ev = _text("scripts/ci_evidence.py")
    assert "latest-success.json" in src
    assert "ci_evidence.py\" verify" in src
    assert "attempts" in ev
    assert "os.replace" in ev
    assert "hashlib.sha256" in ev
    assert "read(_CHUNK)" in ev
    assert "upload-artifact" not in src


def test_merge_only_exige_evidencia_integra_e_revalida_governanca():
    src = _text("scripts/ci-fallback.sh")
    refresh = src[src.index("refresh_status_from_evidence() {") : src.index("attempt_merge() {")]
    assert refresh.index("local_evidence_is_green") < refresh.index("revalidate_governance_for_merge")
    assert refresh.index("revalidate_governance_for_merge") < refresh.index("publish_success_statuses")
    assert "Check Run exato desta promoção" in refresh

    attempt = src[src.index("attempt_merge() {") : src.index("preflight_app_credential\n")]
    assert "refresh_status_from_evidence" in attempt
    assert 'headRefOid)" = "$SHA"' in attempt
    assert "retencao-humana" in attempt
    assert "migration com patch indisponível/truncado" in attempt
    assert "migration potencialmente destrutiva" in attempt
    assert 'repos/$REPO/pulls/$PR/merge' in attempt
    assert '-f sha="$SHA"' in attempt


def test_watcher_incremental_e_falha_de_api_nao_vira_verde():
    src = _text("scripts/ci-fallback-watch.sh")
    assert "local_evidence_green" in src
    assert "--merge-only" in src
    assert "--promote-only" in src
    assert "EJC_FALLBACK_RETRY_FAILED" in src
    assert "GREEN_RECHECK_SECONDS" in src
    assert "pr_state_due" in src
    assert "gh auth status" in src
    assert "GitHub/fetch indisponível" in src
    assert "API de PR indisponível" in src
    assert "git merge --ff-only origin/main" in src
    assert "git reset --hard" not in src
    assert "git push --force" not in src


def test_ativacao_transacional_usa_drain_lock_e_restore_exato():
    src = _text("scripts/ci-fallback-activate.sh")
    assert "/opt/ejc" in src
    assert "docker info" in src
    assert "rollback_activation" in src
    assert "create_drain_marker" in src
    assert "flock -w 120 8" in src
    disable = src[src.index('if [ "$MODE" = "--disable" ]') : src.index('[ "$MODE" = "--enable" ]')]
    assert disable.index("branch-protection.sh --restore") < disable.index("remove_watcher")
    assert "drain mantido" in disable
    assert "branch-protection.sh --cloud" not in disable


def test_branch_protection_modifica_somente_required_status_checks():
    src = _text("scripts/governanca/branch-protection.sh")
    executable = src.split("cat <<'FIM'", 1)[0]
    assert 'protection/required_status_checks' in executable
    assert 'gh api -X PATCH "$API"' in executable
    assert "-X PUT" not in executable
    assert "EJC Local Full Gate" in executable
    assert "app_id" in executable
    assert "required_pull_request_reviews" not in executable
    assert "restrictions" not in executable


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


def test_governanca_local_secret_scan_e_paths_sao_fail_closed_e_nul_safe():
    src = _text("scripts/governanca/ci-local-governanca.sh")
    assert "git diff --name-only -z" in src
    assert "read -r -d ''" in src
    assert 'grep -EIn "$PADROES" -- "$f"' in src
    assert ".env.example" in src
    assert '.env*|*/.env*' in src
    assert "*.min.js" not in src
    assert "*.map" not in src
    assert "*.svg" not in src
    assert "*.lock" not in src
    assert "security-auditor: executado" in src
    assert "MIGRATION_RESERVATIONS.md" in src
    assert "branch de origem protegida" in src
