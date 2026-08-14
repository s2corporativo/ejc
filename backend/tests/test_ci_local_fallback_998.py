from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _block(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def test_componentes_do_fallback_tem_sintaxe_valida():
    bash_scripts = (
        "scripts/ci-local.sh",
        "scripts/ci-fallback.sh",
        "scripts/ci-fallback-watch.sh",
        "scripts/ci-fallback-activate.sh",
        "scripts/ci-worker-isolation.sh",
        "scripts/github-app-auth.sh",
        "scripts/governanca/ci-local-governanca.sh",
        "scripts/governanca/branch-protection.sh",
    )
    for path in bash_scripts:
        proc = subprocess.run(
            ["bash", "-n", str(ROOT / path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"{path}: {proc.stderr}"

    for path in ("scripts/ci_evidence.py", "scripts/ci_activation_journal.py"):
        proc = subprocess.run(
            ["python3", "-m", "py_compile", str(ROOT / path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"{path}: {proc.stderr}"


def test_control_plane_recusa_producao_e_delega_codigo_do_pr_ao_worker():
    src = _text("scripts/ci-fallback.sh")
    assert "/opt/ejc" in src
    assert '"${APP_ENV:-}" != production' in src
    assert '"${EJC_ENV:-}" != production' in src
    assert '"$(id -u)" -ne 0' in src
    assert 'git merge-base --is-ancestor origin/main "$SHA"' in src
    assert '"$(git rev-parse FETCH_HEAD)" = "$SHA"' in src
    assert "EJC_ALLOW_PYTHON_MISMATCH=1 é somente diagnóstico" in src
    assert 'bash "$ROOT/scripts/ci-worker-isolation.sh" preflight' in src

    worker = _block(src, "run_worker_stage() {", "run_governance_stage() {")
    assert 'ci-worker-isolation.sh" run-stage --sha "$SHA" --stage "$key"' in worker
    assert 'EJC_CI_STATE_ROOT="$STATE_ROOT"' in worker
    assert "bash scripts/ci-local.sh backend" not in src
    assert "bash scripts/ci-local.sh frontend" not in src


def test_governanca_e_trusted_e_le_apenas_snapshot_do_pr():
    src = _text("scripts/ci-fallback.sh")
    governance = _block(src, "run_governance() {", "revalidate_governance_for_merge() {")
    assert 'EJC_GOV_SOURCE_ROOT="$GOV_WORKTREE"' in governance
    assert 'bash "$ROOT/scripts/governanca/ci-local-governanca.sh"' in governance
    assert 'git worktree add --detach "$GOV_WORKTREE" "$SHA"' in src

    gov = _text("scripts/governanca/ci-local-governanca.sh")
    assert "EJC_GOV_SOURCE_ROOT" in gov
    assert "ci-worker-isolation" in gov
    assert "ci_evidence" in gov
    assert "github-app-auth" in gov
    # A auditoria de segurança usa diretório de evidência autenticada do
    # security-auditor vinculado ao HEAD SHA (não imprime marcador fixo).
    assert "security-auditor-evidence" in gov
    assert "EVIDENCE_SHA" in gov
    assert "git diff --name-only -z" in gov
    assert 'git show HEAD:"$f"' in gov


def test_full_gate_exige_check_run_exato_app_sha_external_id_e_latest():
    src = _text("scripts/ci-fallback.sh")
    gate = _block(src, "full_gate_is_green() {", "publish_success_statuses() {")
    assert 'check-runs/$FULL_CHECK_ID' in gate
    assert '.head_sha==$sha' in gate
    assert '.external_id==$external_id' in gate
    assert '.app.id==$app_id' in gate
    assert '.status=="completed"' in gate
    assert '.conclusion=="success"' in gate
    assert "latest_full_check_id" in gate
    assert '[ "$latest" = "$FULL_CHECK_ID" ]' in gate


def test_full_gate_so_publica_depois_dos_oito_gates_e_evidencia_promovida():
    src = _text("scripts/ci-fallback.sh")
    finish = src.index('finish_attempt success "" 0 1')
    publish = src.rindex("publish_success_statuses")
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
        assert src.index(marker) < finish < publish


def test_falha_de_stage_nao_publica_sucesso_parcial():
    src = _text("scripts/ci-fallback.sh")
    block = _block(src, "run_worker_stage() {", "run_governance_stage() {")
    assert "finish_attempt failure" in block
    assert 'post_status failure "$context"' in block
    assert "post_full_check failure" in block
    assert "post_status success" not in block
    assert "post_full_check success" not in block


def test_merge_revalida_main_evidencia_gate_protecao_review_e_sha_duas_vezes():
    src = _text("scripts/ci-fallback.sh")
    snapshot = _block(src, "verify_merge_snapshot() {", "attempt_merge() {")
    merge = _block(src, "attempt_merge() {", "run_worker_stage() {")

    for marker in (
        "git fetch --quiet origin main",
        'git merge-base --is-ancestor origin/main "$SHA"',
        "local_evidence_is_green",
        "full_gate_is_green",
        "verify_branch_protection_for_merge",
        "reviewDecision",
        "headRefOid",
        "retencao-humana",
    ):
        assert marker in snapshot
    assert '[ "$review_decision" = APPROVED ]' in snapshot
    assert merge.count("verify_merge_snapshot") >= 2
    assert "migration com patch indisponível/truncado" in merge
    assert "migration potencialmente destrutiva" in merge
    assert 'repos/$REPO/pulls/$PR/merge' in merge
    assert '-f sha="$SHA"' in merge


def test_branch_protection_live_e_verificada_antes_do_merge():
    src = _text("scripts/ci-fallback.sh")
    block = _block(src, "verify_branch_protection_for_merge() {", "verify_merge_snapshot() {")
    for marker in (
        ".required_status_checks.strict==true",
        ".required_status_checks.checks[]?",
        '.context==$name and .app_id==$app_id',
        ".enforce_admins.enabled==true",
        ".required_pull_request_reviews.required_approving_review_count",
        "require_code_owner_reviews",
        "require_last_push_approval",
        "required_conversation_resolution.enabled==true",
        "required_linear_history.enabled==true",
        "allow_force_pushes.enabled==false",
        "allow_deletions.enabled==false",
    ):
        assert marker in block


def test_ci_local_mantem_db_loopback_scram_estado_confinado_e_tooling_separado():
    src = _text("scripts/ci-local.sh")
    assert '127.0.0.1:$PG_PORT:5432' in src
    assert '-p "$PG_PORT:5432"' not in src
    assert 's.bind(("127.0.0.1", 0))' in src
    assert "--auth-host=scram-sha-256" in src
    assert "assert_state_root" in src
    assert 'assert_state_child "$PGDATA" "PGDATA"' in src
    assert 'PIP_AUDIT_VERSION="${PIP_AUDIT_VERSION:-2.10.0}"' in src
    assert "pip-audit" in src
    assert "rm -rf" not in src


def test_watcher_reexecuta_apenas_falha_qualificada_de_infraestrutura():
    src = _text("scripts/ci-fallback-watch.sh")
    for marker in (
        "local_evidence_green",
        "--merge-only",
        "--promote-only",
        "GREEN_RECHECK_SECONDS",
        "pr_state_due",
        "failure_is_infrastructure",
        "latest_attempt_log",
        "GitHub/fetch indisponível",
        "git merge --ff-only origin/main",
    ):
        assert marker in src
    assert "invocation_log" not in src
    assert "git reset --hard" not in src
    assert "git push --force" not in src
    assert "reprovou em teste/gate real; mesmo SHA não será repetido automaticamente" in src


def test_branch_protection_modifica_somente_required_status_checks():
    src = _text("scripts/governanca/branch-protection.sh")
    # Região executável expurgando comentários: o cabeçalho/rodapé citam
    # "restrictions" apenas para documentar que NÃO a alteram.
    executable_parts = src.split("cat <<'FIM'")
    executable = executable_parts[0] + executable_parts[1].split("FIM", 1)[1]
    executable = "\n".join(
        linha for linha in executable.splitlines() if not linha.strip().startswith("#")
    )
    assert "protection/required_status_checks" in executable
    assert 'gh api -X PATCH "$API"' in executable
    assert "-X PUT" not in executable
    assert "EJC Local Full Gate" in executable
    assert "required_pull_request_reviews" not in executable
    assert "restrictions" not in executable


def test_ci_local_cobre_paridade_minima_dos_gates_atuais():
    src = _text("scripts/ci-local.sh")
    required = (
        '"$PY" -m ruff check',
        "--cov-fail-under=65",
        "app.eval.run_eval --smoke",
        "app.eval.agent_trajectory",
        "npm run format:check",
        "npm run test -- --reporter=dot",
        "npm audit --audit-level=high",
        "scripts/ci_guard.sh",
        "test_backup_wrapper.sh",
        "test_deploy_rollback.sh",
        "test_generate_architecture_inventory",
        "restore_drill.py",
        "npm run lint:eslint",
        "playwright install chromium",
        "npm run test:responsive",
        "npm run test:premium-responsive",
    )
    for marker in required:
        assert marker in src, marker
