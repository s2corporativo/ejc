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

    python_proc = subprocess.run(
        ["python3", "-m", "py_compile", str(ROOT / "scripts/ci_evidence.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert python_proc.returncode == 0, python_proc.stderr


def test_executor_recusa_producao_e_estado_dentro_do_checkout():
    source = _text("scripts/ci-fallback.sh")

    for marker in (
        "/opt/ejc/.deployed_sha",
        "/opt/ejc/.env",
        '"${APP_ENV:-}" != "production"',
        '"${EJC_ENV:-}" != "production"',
        '"$(id -u)" -ne 0',
        "ejc_worker",
        "assert_state_path",
    ):
        assert marker in source
    assert 'git merge-base --is-ancestor origin/main "$SHA"' in source
    assert 'git worktree add --detach "$WORKTREE" "$SHA"' in source
    assert '"$(git rev-parse FETCH_HEAD)" = "$SHA"' in source


def test_runtime_divergente_nao_pode_publicar_gate_promovivel():
    source = _text("scripts/ci-fallback.sh")

    assert 'EJC_ALLOW_PYTHON_MISMATCH:-0}" = "1"' in source
    assert "não pode publicar status promovível" in source
    for mode in ("backend", "eval", "continuity"):
        assert f"EJC_ALLOW_PYTHON_MISMATCH=0 bash scripts/ci-local.sh {mode}" in source


def test_full_gate_tem_identidade_de_app_sha_external_id_e_latest_run():
    source = _text("scripts/ci-fallback.sh")
    full_gate = _block(source, "full_gate_is_green() {", "publish_success_statuses() {")

    assert 'repos/$REPO/check-runs/$FULL_CHECK_ID' in full_gate
    assert '.head_sha == $sha' in full_gate
    assert '.external_id == $external_id' in full_gate
    assert '.app.id == $app_id' in full_gate
    assert '.status == "completed"' in full_gate
    assert '.conclusion == "success"' in full_gate
    assert "latest_full_check_id" in full_gate
    assert '[ "$latest" = "$FULL_CHECK_ID" ]' in full_gate


def test_preflight_de_credencial_nao_cria_check_run_neutro_descartavel():
    source = _text("scripts/ci-fallback.sh")
    preflight = _block(source, "preflight_app_credential() {", "post_full_check() {")

    assert "ejc_github_app_refresh" in preflight
    assert "check-runs" not in preflight


def test_sucesso_remoto_so_e_publicado_depois_dos_oito_gates():
    source = _text("scripts/ci-fallback.sh")
    final_publish = source.rindex("publish_success_statuses")
    markers = (
        "run_stage backend",
        "run_stage eval",
        "run_stage frontend",
        "run_stage p0",
        "run_stage governanca",
        "run_stage architecture",
        "run_stage continuity",
        "run_stage ui-extra",
        'finish_attempt success "" 0 1',
        "revalidate_governance_for_merge",
    )
    for marker in markers:
        assert marker in source
        assert source.index(marker) < final_publish


def test_falha_de_stage_nunca_publica_sucesso_parcial():
    source = _text("scripts/ci-fallback.sh")
    block = _block(source, "run_stage() {", "run_stage backend ")

    assert "finish_attempt failure" in block
    assert 'post_status failure "$context"' in block
    assert 'post_full_check failure' in block
    assert "post_status success" not in block
    assert "post_full_check success" not in block


def test_merge_revalida_main_review_protecao_e_gate_duas_vezes():
    source = _text("scripts/ci-fallback.sh")
    snapshot = _block(source, "verify_merge_snapshot() {", "attempt_merge() {")
    merge = _block(source, "attempt_merge() {", "preflight_app_credential\n")

    assert "git fetch --quiet origin main" in snapshot
    assert 'git merge-base --is-ancestor origin/main "$SHA"' in snapshot
    assert "local_evidence_is_green" in snapshot
    assert "full_gate_is_green" in snapshot
    assert "verify_branch_protection_for_merge" in snapshot
    assert 'reviewDecision' in snapshot
    assert '[ "$review_decision" = "APPROVED" ]' in snapshot
    assert 'headRefOid' in snapshot
    assert "retencao-humana" in snapshot

    assert merge.count("verify_merge_snapshot") >= 2
    assert 'repos/$REPO/pulls/$PR/merge' in merge
    assert '-f sha="$SHA"' in merge
    assert "migration potencialmente destrutiva" in merge


def test_branch_protection_e_conferida_antes_do_merge():
    source = _text("scripts/ci-fallback.sh")
    block = _block(
        source, "verify_branch_protection_for_merge() {", "verify_merge_snapshot() {"
    )

    for marker in (
        ".required_status_checks.strict == true",
        'EJC Local Full Gate',
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


def test_ci_local_mantem_pg_loopback_e_sem_operacoes_destrutivas_de_fs():
    source = _text("scripts/ci-local.sh")

    assert '127.0.0.1:$PG_PORT:5432' in source
    assert '-p "$PG_PORT:5432"' not in source
    assert 's.bind(("127.0.0.1", 0))' in source
    assert "safe_remove_tree" in source
    assert 'find "$path" -depth -mindepth 1 -delete' in source
    assert "rm -rf" not in source


def test_ci_local_cobre_paridade_minima_dos_workflows_atuais():
    source = _text("scripts/ci-local.sh")
    required = (
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
    )
    for marker in required:
        assert marker in source, marker


def test_ativador_drena_sem_matar_produtor_antes_de_restaurar_protecao():
    source = _text("scripts/ci-fallback-activate.sh")
    disable = source[
        source.index('if [ "$MODE" = "--disable" ]') : source.index(
            '[ "$MODE" = "--enable" ]'
        )
    ]

    assert "create_drain_marker" in disable
    assert "flock -w 120" in disable
    assert "branch-protection.sh --restore" in disable
    assert "remove_watcher" in disable
    assert disable.index("branch-protection.sh --restore") < disable.index("remove_watcher")
    restore_failure = disable[disable.index("if ! EJC_BRANCH_PROTECTION_BACKUP") :]
    assert 'rm -f "$DRAIN_FILE"' in restore_failure
    assert "watcher preservado" in restore_failure


def test_governanca_local_continua_fail_closed_para_segredos_e_ci_sensivel():
    source = _text("scripts/governanca/ci-local-governanca.sh")

    assert "git diff --name-only -z" in source
    assert "read -r -d ''" in source
    assert 'grep -EIn "$PADROES" -- "$f"' in source
    assert ".env.example" in source
    assert "security-auditor: executado" in source
    assert "MIGRATION_RESERVATIONS.md" in source
    assert "branch de origem protegida" in source
