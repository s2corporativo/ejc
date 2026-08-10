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

    # A proteção fallback exige somente o agregado; statuses detalhados locais
    # são observabilidade e não podem virar dependência permanente da main.
    assert '"contexts": [\n      "EJC Local Full Gate"\n    ]' in protection
