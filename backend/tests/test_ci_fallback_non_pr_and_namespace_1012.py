from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FALLBACK = ROOT / "scripts" / "ci-fallback.sh"


def _block(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def test_execucao_sem_pr_preserva_governanca_pre_push_sem_exigir_pr():
    source = FALLBACK.read_text(encoding="utf-8")
    block = _block(source, "run_governance() {", "revalidate_governance_for_merge() {")

    assert 'if [ -n "$PR" ]' in block
    assert 'EJC_GOV_REQUIRE_PR=1' in block
    assert 'EJC_PR_NUMBER="$PR"' in block
    assert 'EJC_GOV_REQUIRE_PR=0' in block


def test_full_gate_nao_e_reutilizado_como_commit_status_informativo():
    source = FALLBACK.read_text(encoding="utf-8")

    assert "CONTEXT_ARCH='EJC Local / Arquitetura'" in source
    assert "CONTEXT_CONT='EJC Local / Continuidade'" in source
    assert "CONTEXT_UI='EJC Local / UI Extra'" in source
    assert 'run_worker_stage architecture "$CONTEXT_ARCH"' in source
    assert 'run_worker_stage continuity "$CONTEXT_CONT"' in source
    assert 'run_worker_stage ui-extra "$CONTEXT_UI"' in source

    stage_block = _block(source, "run_worker_stage() {", "run_governance_stage() {")
    assert 'post_status failure "$context"' in stage_block
    assert 'post_status failure "$CONTEXT_FULL"' not in source
