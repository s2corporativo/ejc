from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_fallback_nao_publica_contexts_canônicos_do_actions():
    fallback = (ROOT / "scripts" / "ci-fallback.sh").read_text(encoding="utf-8")
    protection = (
        ROOT / "scripts" / "governanca" / "branch-protection.sh"
    ).read_text(encoding="utf-8")

    cloud_contexts = (
        "Backend — suíte completa + schema/RAG (Postgres pgvector)",
        "Eval — smoke dos gold sets (offline, bloqueante)",
        "Frontend — testes + typecheck + build",
        "P0 guard — conflitos e segredos",
        "Governança — travas de PR",
    )
    for context in cloud_contexts:
        assert context in protection
        assert context not in fallback

    local_contexts = (
        "EJC Local / Backend",
        "EJC Local / Eval",
        "EJC Local / Frontend",
        "EJC Local / P0 Guard",
        "EJC Local / Governança",
        "EJC Local Full Gate",
    )
    for context in local_contexts:
        assert context in fallback

    # O gate promovível usa required_status_checks.checks vinculado ao app_id.
    # Statuses clássicos dos subgates são apenas observabilidade.
    build = protection[
        protection.index("build_fallback_payload() {") : protection.index(
            'if [ "$MODO" = "--contextos" ]'
        )
    ]
    assert 'checks: [' in build
    assert '{context: "EJC Local Full Gate", app_id: $app_id}' in build
    assert 'contexts:' not in build


def test_watcher_sem_auto_merge_repromove_status_sem_tentar_integracao():
    fallback = (ROOT / "scripts" / "ci-fallback.sh").read_text(encoding="utf-8")
    watcher = (ROOT / "scripts" / "ci-fallback-watch.sh").read_text(encoding="utf-8")

    assert "--promote-only" in fallback
    assert "--promote-only" in watcher
    assert "PROMOTE_ONLY=1" in fallback

    approved = watcher[watcher.index('if local_evidence_green "$sha"; then') :]
    approved = approved[: approved.index("continue")]
    assert 'if [ "$AUTO_MERGE" = "1" ]; then' in approved
    assert "--merge-only" in approved
    assert "--promote-only" in approved
