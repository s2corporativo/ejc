from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WATCHER = ROOT / "scripts" / "ci-fallback-watch.sh"


def test_drain_e_avaliado_antes_de_qualquer_acesso_a_pr():
    src = WATCHER.read_text(encoding="utf-8")
    run_cycle = src[src.index("run_cycle() {") :]
    drain = run_cycle.index('[ -e "$DRAIN_FILE" ]')
    auth = run_cycle.index("gh auth status")
    pr_list = run_cycle.index("gh pr list")
    assert drain < auth < pr_list


def test_green_recheck_evitar_churn_de_api_em_pr_inalterado():
    src = WATCHER.read_text(encoding="utf-8")
    assert "GREEN_RECHECK_SECONDS" in src
    assert "pr_state_due" in src
    assert "write_pr_state" in src
    assert "$sha|$updated_at|$merge_state|$AUTO_MERGE" in src


def test_lock_busy_e_tempfail_nao_viram_falha_de_codigo():
    src = WATCHER.read_text(encoding="utf-8")
    assert '[ "$rc" -eq 75 ]' in src
    busy_block = src[src.index('if [ "$rc" -eq 75 ]') :]
    assert "pending" in busy_block
