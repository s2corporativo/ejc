from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVATE = ROOT / "scripts" / "ci-fallback-activate.sh"


def _source() -> str:
    return ACTIVATE.read_text(encoding="utf-8")


def _block(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end)]


def test_flags_de_rollback_sao_marcados_antes_das_mutacoes():
    source = _source()

    watcher_flag = source.index("WATCHER_TOUCHED=1")
    watcher_mutation = source.index('install_watcher "$SCHEDULER"')
    hooks_flag = source.index("HOOKS_TOUCHED=1")
    hooks_mutation = source.index("git config --local core.hooksPath .githooks")
    protection_flag = source.index("PROTECTION_TOUCHED=1")
    protection_mutation = source.index("branch-protection.sh --fallback")

    assert watcher_flag < watcher_mutation
    assert hooks_flag < hooks_mutation
    assert protection_flag < protection_mutation


def test_rollback_restaura_protecao_antes_de_remover_produtor():
    source = _source()
    rollback = _block(source, "rollback_enable() {", "trap rollback_enable EXIT")

    restore = rollback.index("branch-protection.sh --restore")
    remove = rollback.index("remove_watcher")
    assert restore < remove


def test_falha_de_restore_preserva_snapshot_watcher_e_drain():
    source = _source()
    rollback = _block(source, "rollback_enable() {", "trap rollback_enable EXIT")
    failure = rollback[
        rollback.index('if [ "$protection_restored" -eq 0 ]') : rollback.index(
            'if [ "$WATCHER_TOUCHED" -eq 1 ]'
        )
    ]

    assert "preserve_recovery_state" in failure
    assert "snapshot foram preservados" in failure
    assert 'rm -f "$PROTECTION_BACKUP"' not in failure
    assert "remove_watcher" not in failure


def test_snapshot_so_e_removido_depois_de_rollback_integral():
    source = _source()
    rollback = _block(source, "rollback_enable() {", "trap rollback_enable EXIT")

    remove_snapshot = rollback.rindex('rm -f "$PROTECTION_BACKUP"')
    restore = rollback.index("branch-protection.sh --restore")
    remove_watcher = rollback.index("remove_watcher")
    restore_hooks = rollback.index("restore_hooks_path")

    assert restore < remove_watcher < restore_hooks < remove_snapshot
