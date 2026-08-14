from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "governanca" / "branch-protection.sh"


def test_branch_protection_nao_reconstroi_politica_completa():
    src = SCRIPT.read_text(encoding="utf-8")
    executable = src.split("cat <<'FIM'", 1)[0]
    assert 'protection/required_status_checks' in src
    assert 'gh api -X PATCH "$API"' in src
    assert "-X PUT" not in executable
    for field in (
        "required_pull_request_reviews",
        "enforce_admins",
        "required_linear_history",
        "allow_force_pushes",
        "allow_deletions",
        "required_conversation_resolution",
    ):
        assert field not in executable


def test_fallback_exige_backup_anterior_sem_sobrescrever():
    src = SCRIPT.read_text(encoding="utf-8")
    assert '[ ! -e "$BACKUP_FILE" ]' in src
    assert "recuse sobrescrita" in src
    assert "--restore" in src
