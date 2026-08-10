from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _heredoc_payload(text: str, name: str) -> dict:
    match = re.search(
        rf"read -r -d '' {re.escape(name)} <<'JSON' \|\| true\n(.*?)\nJSON",
        text,
        flags=re.DOTALL,
    )
    assert match, f"payload {name} não localizado"
    return json.loads(match.group(1))


def test_scripts_fallback_tem_sintaxe_bash_valida():
    paths = [
        "scripts/ci-local.sh",
        "scripts/ci-fallback.sh",
        "scripts/ci-fallback-watch.sh",
        "scripts/ci-fallback-activate.sh",
        "scripts/governanca/ci-local-governanca.sh",
        "scripts/governanca/branch-protection.sh",
    ]
    for path in paths:
        proc = subprocess.run(
            ["bash", "-n", str(ROOT / path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"{path}: {proc.stderr}"


def test_fallback_recusa_producao_root_e_exige_sha_atualizado():
    src = _text("scripts/ci-fallback.sh")
    assert "/opt/ejc" in src
    assert '"${APP_ENV:-}" != "production"' in src
    assert '"${EJC_ENV:-}" != "production"' in src
    assert '"$(id -u)" -ne 0' in src
    assert 'git merge-base --is-ancestor origin/main "$SHA"' in src
    assert 'git worktree add --detach "$WORKTREE" "$SHA"' in src
    assert '"$(git rev-parse FETCH_HEAD)" = "$SHA"' in src


def test_ci_local_recusa_host_produtivo_e_expoe_pg_so_no_loopback():
    src = _text("scripts/ci-local.sh")
    assert "/opt/ejc/.deployed_sha" in src
    assert "/opt/ejc/.env" in src
    for name in ("ejc_backend", "ejc_db", "ejc_frontend", "ejc_redis"):
        assert name in src
    assert '127.0.0.1:$PG_PORT:5432' in src
    assert '-p "$PG_PORT:5432"' not in src


def test_contexto_full_so_fica_verde_depois_de_todos_os_gates():
    src = _text("scripts/ci-fallback.sh")
    success = 'post_status success "$CONTEXT_FULL"'
    assert src.count(success) == 1
    pos_success = src.index(success)
    for marker in (
        "run_stage backend",
        "run_stage eval",
        "run_stage frontend",
        "run_stage p0",
        "run_stage governanca",
        "run_stage architecture",
        "run_stage continuity",
        "run_stage ui-extra",
    ):
        assert marker in src
        assert src.index(marker) < pos_success


def test_falha_de_stage_publica_failure_e_nao_success_parcial():
    src = _text("scripts/ci-fallback.sh")
    block = src[src.index("run_stage() {") : src.index("# Chamamos scripts via bash")]
    assert 'post_status failure "$context"' in block
    assert 'post_status failure "$CONTEXT_FULL"' in block
    assert "post_status success" not in block


def test_logs_completos_ficam_locais_e_resumo_guarda_hashes():
    src = _text("scripts/ci-fallback.sh")
    assert ".cache/ejc-ci-evidence" in src
    assert 'chmod 700 "$EVIDENCE"' in src
    assert 'hashlib.sha256(p.read_bytes()).hexdigest()' in src
    assert '"bytes": p.stat().st_size' in src
    assert "upload-artifact" not in src
    assert "gh pr comment" not in src


def test_merge_so_usa_gate_full_do_sha_exato_e_respeita_excecoes():
    src = _text("scripts/ci-fallback.sh")
    assert "full_gate_is_green" in src
    assert 'select(.context == $c)][0].state' in src
    assert 'headRefOid)" = "$SHA"' in src
    assert "retencao-humana" in src
    assert "migration potencialmente destrutiva" in src
    assert 'repos/$REPO/pulls/$PR/merge' in src
    assert '-f sha="$SHA"' in src


def test_watcher_nao_repete_suite_aprovada_e_reavalia_merge():
    src = _text("scripts/ci-fallback-watch.sh")
    success_block_start = src.index("if [ -f \"$marker\" ] && grep -qx 'success'")
    success_block_end = src.index("fi", success_block_start)
    block = src[success_block_start:success_block_end]
    assert "--merge-only" in block
    assert 'bash "$ROOT/scripts/ci-fallback.sh"' in src
    assert "EJC_FALLBACK_RETRY_FAILED" in src


def test_watcher_nao_morre_com_api_fora_e_so_atualiza_main_por_fast_forward():
    src = _text("scripts/ci-fallback-watch.sh")
    assert "gh auth status" in src
    assert "GitHub/fetch indisponível" in src
    assert "API de PR indisponível" in src
    assert "git merge --ff-only origin/main" in src
    assert "git reset --hard" not in src
    assert "git push --force" not in src


def test_ativacao_e_reversao_nao_usam_runner_de_producao():
    src = _text("scripts/ci-fallback-activate.sh")
    assert "/opt/ejc" in src
    assert "/opt/ejc/.deployed_sha" in src
    assert '"$(id -u)" -ne 0' in src
    assert "docker info" in src
    assert "gh auth status" in src
    assert "branch-protection.sh --fallback" in src
    assert "branch-protection.sh --cloud" in src
    assert "systemctl --user" in src
    assert "self-hosted" not in src.lower()


def test_ativacao_e_transacional_e_disable_restaura_cloud_antes_de_parar_watcher():
    src = _text("scripts/ci-fallback-activate.sh")
    assert "rollback_activation" in src
    assert "PROTECTION_CHANGED=1" in src
    assert "ativação falhou; restaurando branch protection cloud" in src
    disable_start = src.index('if [ "$MODE" = "--disable" ]')
    disable_end = src.index('fi\n[ "$MODE" = "--enable" ]', disable_start)
    disable = src[disable_start:disable_end]
    assert disable.index("branch-protection.sh --cloud") < disable.index("remove_watcher")
    assert '"$(git branch --show-current)" = "main"' in src
    assert '"$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"' in src


def test_branch_protection_fallback_troca_so_contexto_e_preserva_travas():
    src = _text("scripts/governanca/branch-protection.sh")
    payload = _heredoc_payload(src, "PAYLOAD_FALLBACK")
    checks = payload["required_status_checks"]
    assert checks["strict"] is True
    assert checks["contexts"] == ["EJC Local Full Gate"]
    assert "checks" not in checks
    assert payload["enforce_admins"] is True
    reviews = payload["required_pull_request_reviews"]
    assert reviews["required_approving_review_count"] == 1
    assert reviews["require_code_owner_reviews"] is True
    assert reviews["dismiss_stale_reviews"] is True
    assert reviews["require_last_push_approval"] is True
    assert payload["required_conversation_resolution"] is True
    assert payload["required_linear_history"] is True
    assert payload["allow_force_pushes"] is False
    assert payload["allow_deletions"] is False


def test_ci_local_cobre_paridade_minima_dos_workflows_atuais():
    src = _text("scripts/ci-local.sh")
    required = [
        '"$PY" -m ruff check',
        "pip-audit",
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
        "playwright install --with-deps chromium",
        "npm run test:responsive",
        "npm run test:premium-responsive",
    ]
    for marker in required:
        assert marker in src, marker


def test_governanca_local_replica_travas_criticas_sem_segredos():
    src = _text("scripts/governanca/ci-local-governanca.sh")
    assert "MIGRATION_RESERVATIONS.md" in src
    assert "PRIVATE KEY" in src
    assert "\.env" in src
    assert "security-auditor: executado" in src
    assert 'BRANCH" != "main"' in src
    assert "Issue vinculada" in src
    assert "Riscos residuais" in src
    assert "Rollback" in src
