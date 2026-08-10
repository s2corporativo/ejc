from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FALLBACK = ROOT / "scripts" / "ci-fallback.sh"
WATCHER = ROOT / "scripts" / "ci-fallback-watch.sh"
ACTIVATE = ROOT / "scripts" / "ci-fallback-activate.sh"
PROTECTION = ROOT / "scripts" / "governanca" / "branch-protection.sh"


def test_fallback_serializa_por_sha_e_nao_aceita_check_historico():
    src = FALLBACK.read_text(encoding="utf-8")
    assert 'LOCK_FILE="$SHA_EVIDENCE/.lock"' in src
    assert "flock -n 9" in src
    assert 'check-runs/$FULL_CHECK_ID' in src
    assert 'commits/$SHA/check-runs?per_page=100' not in src


def test_migration_diff_falha_fechado_quando_patch_indisponivel():
    src = FALLBACK.read_text(encoding="utf-8")
    assert 'pulls/$PR/files?per_page=100' in src
    assert 'select(.patch == null)' in src
    assert 'migration com patch indisponível/truncado' in src
    assert 'gh pr diff "$PR" --repo "$REPO" || true' not in src


def test_promocao_exige_docker_e_evidencia_content_addressed():
    src = FALLBACK.read_text(encoding="utf-8")
    assert 'Docker é obrigatório para fallback promovível' in src
    assert 'scripts/ci_evidence.py" verify' in src
    assert 'latest-success.json' in src


def test_watcher_respeita_drain_lock_temporario_e_fingerprint_incremental():
    src = WATCHER.read_text(encoding="utf-8")
    assert 'DRAIN_FILE=' in src
    assert 'drain ativo; ciclo pulado' in src
    assert '[ "$rc" -eq 75 ]' in src
    assert 'fingerprint="$sha|$updated_at|$merge_state|$AUTO_MERGE"' in src
    assert 'GREEN_RECHECK_SECONDS' in src


def test_disable_restaura_checks_sob_lock_antes_de_remover_scheduler():
    src = ACTIVATE.read_text(encoding="utf-8")
    disable = src[src.index('if [ "$MODE" = "--disable" ]'): src.index('[ "$MODE" = "--enable" ]')]
    assert "create_drain_marker" in disable
    assert "flock -w 120 8" in disable
    assert "branch-protection.sh --restore" in disable
    assert "remove_watcher" in disable
    assert disable.index("branch-protection.sh --restore") < disable.index("remove_watcher")


def test_branch_protection_altera_somente_required_status_checks():
    src = PROTECTION.read_text(encoding="utf-8")
    executable = src.split("cat <<'FIM'", 1)[0]
    assert 'required_status_checks' in src
    assert '-X PATCH "$API"' in src
    assert '-X PUT' not in executable
    assert 'restrictions' not in executable
