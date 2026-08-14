from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "governanca" / "branch-protection-bootstrap.sh"


def test_bootstrap_exige_autorizacao_e_main():
    src = SCRIPT.read_text(encoding="utf-8")
    assert 'EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION' in src
    assert '[ "$AUTH" = "998" ]' in src
    assert '[ "$BRANCH" = "main" ]' in src


def test_bootstrap_recusa_sobrescrever_protecao_existente():
    src = SCRIPT.read_text(encoding="utf-8")
    assert '.protected // false' in src
    assert '[ "$protected" = "false" ]' in src
    assert "recuso sobrescrever política existente" in src


def test_bootstrap_restaura_baseline_fail_closed_com_codeowners():
    src = SCRIPT.read_text(encoding="utf-8")
    assert 'strict: true' in src
    assert 'enforce_admins: true' in src
    assert 'require_code_owner_reviews: true' in src
    assert 'required_approving_review_count: 1' in src
    assert 'require_last_push_approval: true' in src
    assert 'required_conversation_resolution: true' in src
    assert 'required_linear_history: true' in src
    assert 'allow_force_pushes: false' in src
    assert 'allow_deletions: false' in src
    assert 'restrictions: null' in src


def test_bootstrap_exige_cinco_checks_cloud_e_read_after_write():
    src = SCRIPT.read_text(encoding="utf-8")
    for context in (
        "Backend — suíte completa + schema/RAG (Postgres pgvector)",
        "Eval — smoke dos gold sets (offline, bloqueante)",
        "Frontend — testes + typecheck + build",
        "P0 guard — conflitos e segredos",
        "Governança — travas de PR",
    ):
        assert context in src
    assert 'gh api -X PUT "$PROTECTION_API"' in src
    assert 'current="$(gh api "$PROTECTION_API"' in src
    assert "estado efetivo não corresponde ao baseline fail-closed" in src
