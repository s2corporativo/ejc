from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_fallback_nao_publica_contexts_canonicos_do_actions():
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
        "EJC Local / Arquitetura",
        "EJC Local / Continuidade",
        "EJC Local / UI Extra",
        "EJC Local Full Gate",
    )
    for context in local_contexts:
        assert context in fallback

    build = protection[
        protection.index("build_fallback_payload() {") : protection.index(
            'if [ "$MODO" = "--contextos" ]'
        )
    ]
    compact = "".join(build.split())
    assert "checks:[" in compact
    assert 'context:"EJCLocalFullGate",app_id:$app_id' in compact
    assert "contexts:" not in compact


def test_watcher_sem_auto_merge_repromove_status_sem_tentar_integracao():
    fallback = (ROOT / "scripts" / "ci-fallback.sh").read_text(encoding="utf-8")
    watcher = (ROOT / "scripts" / "ci-fallback-watch.sh").read_text(encoding="utf-8")

    assert "--promote-only" in fallback
    assert "--promote-only" in watcher
    assert "PROMOTE_ONLY=1" in fallback

    approved = watcher[watcher.index('if local_evidence_green "$sha"; then') :]
    # O script atual insere um "continue" de skip no guard de pr_state_due ANTES
    # do bloco de decisão; a região relevante termina no registro de estado da
    # mesma superfície de aprovação (write_pr_state).
    approved = approved[: approved.index("write_pr_state")]
    assert 'if [ "$AUTO_MERGE" = "1" ]' in approved
    assert "--merge-only" in approved
    assert "--promote-only" in approved
