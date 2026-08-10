from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "ci_activation_journal.py"
ACTIVATE = ROOT / "scripts" / "ci-fallback-activate.sh"


def run_tool(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(TOOL), *args],
        check=check,
        text=True,
        capture_output=True,
    )


def begin(root: Path, journal: Path) -> None:
    run_tool(
        "begin",
        "--state-root",
        str(root),
        "--file",
        str(journal),
        "--repo",
        "s2corporativo/ejc",
        "--protection-backup",
        str(root / "protection.json"),
        "--hooks-backup",
        str(root / "hooks.before"),
        "--scheduler",
        "cron",
    )


def test_journal_escrita_atomica_modo_0600_e_fases_monotonicas(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    os.chmod(state, 0o700)
    journal = state / "activation-transaction.json"

    begin(state, journal)
    assert stat.S_IMODE(journal.stat().st_mode) == 0o600
    assert json.loads(journal.read_text())["phase"] == "starting"

    for phase in ("draining", "watcher", "hooks", "protection", "commit", "active"):
        run_tool(
            "phase",
            "--state-root",
            str(state),
            "--file",
            str(journal),
            "--phase",
            phase,
        )
        assert json.loads(journal.read_text())["phase"] == phase

    run_tool("clear", "--state-root", str(state), "--file", str(journal))
    assert not journal.exists()


def test_journal_rejeita_regressao_de_fase_e_adulteracao(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    os.chmod(state, 0o700)
    journal = state / "activation-transaction.json"
    begin(state, journal)
    run_tool(
        "phase",
        "--state-root",
        str(state),
        "--file",
        str(journal),
        "--phase",
        "protection",
    )
    reg = run_tool(
        "phase",
        "--state-root",
        str(state),
        "--file",
        str(journal),
        "--phase",
        "hooks",
        check=False,
    )
    assert reg.returncode != 0

    journal.write_text('{"schema":1,"phase":"active"}\n', encoding="utf-8")
    os.chmod(journal, 0o600)
    bad = run_tool("show", "--state-root", str(state), "--file", str(journal), check=False)
    assert bad.returncode != 0


def test_journal_rejeita_symlink_hardlink_e_permissao_ampla(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    os.chmod(state, 0o700)
    target = state / "target.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, 0o600)

    symlink = state / "activation-transaction.json"
    symlink.symlink_to(target)
    result = run_tool(
        "begin",
        "--state-root",
        str(state),
        "--file",
        str(symlink),
        "--repo",
        "s2corporativo/ejc",
        "--protection-backup",
        str(state / "p"),
        "--hooks-backup",
        str(state / "h"),
        "--scheduler",
        "cron",
        check=False,
    )
    assert result.returncode != 0
    symlink.unlink()

    hard = state / "activation-transaction.json"
    os.link(target, hard)
    shown = run_tool("show", "--state-root", str(state), "--file", str(hard), check=False)
    assert shown.returncode != 0
    hard.unlink()

    os.chmod(state, 0o750)
    wide = run_tool(
        "begin",
        "--state-root",
        str(state),
        "--file",
        str(state / "new.json"),
        "--repo",
        "s2corporativo/ejc",
        "--protection-backup",
        str(state / "p"),
        "--hooks-backup",
        str(state / "h"),
        "--scheduler",
        "cron",
        check=False,
    )
    assert wide.returncode != 0


def test_ativador_falha_fechado_com_journal_e_expoe_recovery_idempotente():
    src = ACTIVATE.read_text(encoding="utf-8")
    assert 'JOURNAL_FILE="$LOG_DIR/activation-transaction.json"' in src
    assert 'journal_begin "$SCHEDULER"' in src
    assert "journal_phase draining" in src
    assert "journal_phase watcher" in src
    assert "journal_phase hooks" in src
    assert "journal_phase protection" in src
    assert "journal_phase commit" in src
    assert "journal_phase active" in src
    assert "recover_incomplete_transaction()" in src
    assert 'state=recovery_required' in src
    assert 'journal incompleto presente; execute --disable para recovery' in src
    assert 'recover_incomplete_transaction \\' in src
    assert "journal_clear" in src


def test_recovery_preserva_snapshot_quando_restore_falha():
    src = ACTIVATE.read_text(encoding="utf-8")
    block = src[src.index("recover_incomplete_transaction()") : src.index('if [ "$MODE" = "--status" ]')]
    restore = block.index("branch-protection.sh --restore")
    remove = block.index("remove_watcher")
    cleanup = block.index('rm -f "$ACTIVE_FILE"')
    assert restore < remove < cleanup
    assert "return 1" in block[restore:remove]
    assert 'rm -f "$PROTECTION_BACKUP"' not in block[:remove]
