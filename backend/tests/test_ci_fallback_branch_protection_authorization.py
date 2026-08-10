from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROTECTION = ROOT / "scripts" / "governanca" / "branch-protection.sh"
ACTIVATE = ROOT / "scripts" / "ci-fallback-activate.sh"
FALLBACK = ROOT / "scripts" / "ci-fallback.sh"


def test_modo_fallback_exige_autorizacao_registrada_998():
    src = PROTECTION.read_text(encoding="utf-8")
    assert 'FALLBACK_AUTHORIZATION="${EJC_FALLBACK_AUTHORIZATION:-}"' in src
    assert '[ "$FALLBACK_AUTHORIZATION" = "998" ]' in src
    assert "modo --fallback exige EJC_FALLBACK_AUTHORIZATION=998" in src


def test_execucao_sem_argumento_e_somente_leitura():
    src = PROTECTION.read_text(encoding="utf-8")
    assert 'MODO="${1:---verificar}"' in src
    assert 'MODO="${1:---cloud}"' not in src
    verify = src[src.index('if [ "$MODO" = "--verificar" ]') :]
    assert "get_status_checks" in verify


def test_ativador_injeta_autorizacao_e_snapshot_exato_sem_bypass():
    src = ACTIVATE.read_text(encoding="utf-8")
    assert "EJC_FALLBACK_AUTHORIZATION=998" in src
    assert 'EJC_FALLBACK_APP_ID="$FALLBACK_APP_ID"' in src
    assert 'EJC_BRANCH_PROTECTION_BACKUP="$PROTECTION_BACKUP"' in src
    assert "branch-protection.sh --fallback" in src
    assert "--force" not in src
    assert "bypass" not in src.lower()


def test_fallback_branch_protection_vincula_check_ao_app_sem_reescrever_restante():
    src = PROTECTION.read_text(encoding="utf-8")
    executable = src.split("cat <<'FIM'", 1)[0]
    assert 'FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"' in src
    assert 'protection/required_status_checks' in src
    assert 'checks: [{context:"EJC Local Full Gate", app_id:$app_id}]' in src
    assert 'gh api -X PATCH "$API"' in src
    assert "-X PUT" not in executable
    assert "required_pull_request_reviews" not in executable
    assert "restrictions" not in executable


def test_snapshot_de_status_checks_recusa_sobrescrita_e_restore_valida_repositorio():
    src = PROTECTION.read_text(encoding="utf-8")
    assert '[ ! -e "$BACKUP_FILE" ]' in src
    assert "recuse sobrescrita" in src
    assert 'repo="$(jq -r' in src
    assert 'branch="$(jq -r' in src
    assert '[ "$repo" = "$REPO" ] && [ "$branch" = "$BRANCH" ]' in src
    assert "apply_status_checks" in src


def test_snapshot_de_branch_protection_fica_fora_do_repo_e_rejeita_redirecionamento():
    src = PROTECTION.read_text(encoding="utf-8")
    assert 'STATE_ROOT="${EJC_CI_STATE_ROOT:-${XDG_CACHE_HOME:-${HOME}/.cache}/ejc-ci-fallback}"' in src
    assert 'BACKUP_FILE="${EJC_BRANCH_PROTECTION_BACKUP:-$STATE_ROOT/required-status-checks-anterior.json}"' in src
    assert "validate_backup_path()" in src
    assert "EJC_CI_STATE_ROOT deve ser caminho absoluto" in src
    assert "snapshot de branch protection deve usar caminho absoluto" in src
    assert "snapshot deve permanecer confinado sob EJC_CI_STATE_ROOT" in src
    assert "snapshot não pode ser gravado dentro do repositório" in src
    assert "componente symlink no caminho" in src
    assert "assert_no_symlink_component" in src
    assert "var/required-status-checks-anterior.json" not in src


def test_full_gate_publica_check_run_exato_e_valida_app_sha_nome_conclusao():
    src = FALLBACK.read_text(encoding="utf-8")
    assert 'FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"' in src
    assert 'repos/$REPO/check-runs' in src
    assert 'repos/$REPO/statuses/$SHA' in src
    assert 'if [ "$context" = "$CONTEXT_FULL" ]' in src
    assert 'check-runs/$FULL_CHECK_ID' in src
    assert '.app.id // -1' in src
    assert '.head_sha // empty' in src
    assert '.name // empty' in src
    assert '.conclusion // empty' in src
    assert 'commits/$SHA/check-runs?per_page=100' not in src


def test_ativador_propaga_identidade_do_app_sem_token_persistido():
    src = ACTIVATE.read_text(encoding="utf-8")
    assert '[[ "$FALLBACK_APP_ID" =~ ^[1-9][0-9]*$ ]]' in src
    assert '[[ "$INSTALLATION_ID" =~ ^[1-9][0-9]*$ ]]' in src
    assert "Environment=\"EJC_FALLBACK_APP_ID=$FALLBACK_APP_ID\"" in src
    assert "Environment=\"EJC_FALLBACK_INSTALLATION_ID=$INSTALLATION_ID\"" in src
    assert "Environment=\"EJC_FALLBACK_APP_PRIVATE_KEY_FILE=$APP_KEY_FILE\"" in src
    assert "GH_TOKEN=" not in src
    assert "GITHUB_TOKEN=" not in src
