from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
ACTIVATE = ROOT / "scripts" / "ci-fallback-activate.sh"


def test_scheduler_autonomo_exige_persistencia_comprovada():
    src = ACTIVATE.read_text(encoding="utf-8")
    assert "cron_persistente()" in src
    assert "pgrep -x cron" in src
    assert "pgrep -x crond" in src
    assert "systemd_user_persistente()" in src
    assert "loginctl show-user" in src
    assert '-p Linger --value' in src
    assert '= "yes" ]' in src

    select = src[
        src.index('SCHEDULER=""') : src.index('ok "scheduler persistente selecionado:')
    ]
    assert select.index("if cron_persistente") < select.index("elif systemd_user_persistente")
    assert "sem scheduler persistente" in select


def test_scheduler_recebe_runtime_e_credencial_por_caminho_sem_token_persistido():
    src = ACTIVATE.read_text(encoding="utf-8")
    assert 'WATCHER_PATH="${EJC_FALLBACK_PATH:-$PATH}"' in src
    assert 'Environment="PATH=$WATCHER_PATH"' in src
    assert "/usr/bin/env PATH='$WATCHER_PATH'" in src
    assert "EJC_ALLOW_PYTHON_MISMATCH=0" in src
    assert "EJC_FALLBACK_APP_ID" in src
    assert "EJC_FALLBACK_INSTALLATION_ID" in src
    assert "EJC_FALLBACK_APP_PRIVATE_KEY_FILE" in src
    assert "GH_TOKEN=" not in src
    assert "GITHUB_TOKEN=" not in src


def test_ativacao_recusa_quoting_ambiguo_do_scheduler():
    src = ACTIVATE.read_text(encoding="utf-8")
    assert "caractere inseguro para scheduler" in src
    assert "*'\"'*" in src
    assert "*'\\'*" in src
    assert "*%*" in src


def test_ativacao_exige_modo_explicito_e_expoe_status():
    src = ACTIVATE.read_text(encoding="utf-8")
    assert 'MODE="${1:-}"' in src
    assert 'uso: $0 --enable | --disable | --status' in src
    assert 'MODE="${1:---enable}"' not in src
    assert 'if [ "$MODE" = "--status" ]' in src


def test_remove_cron_tolera_filtro_vazio_com_pipefail():
    src = ACTIVATE.read_text(encoding="utf-8")
    block = src[src.index("remove_cron() {") : src.index("remove_watcher() {")]
    assert 'grep -vF "$CRON_MARK" || true' in block
    assert "crontab -" in block


def test_disable_e_transacao_drain_restore_remove():
    src = ACTIVATE.read_text(encoding="utf-8")
    block = src[src.index('if [ "$MODE" = "--disable" ]') : src.index('[ "$MODE" = "--enable" ]')]
    assert "create_drain_marker" in block
    assert "flock -w 120 8" in block
    assert "branch-protection.sh --restore" in block
    assert "remove_watcher" in block
    assert block.index("branch-protection.sh --restore") < block.index("remove_watcher")
    assert "drain mantido" in block
    assert "rm -f \"$ACTIVE_FILE\" \"$PROTECTION_BACKUP\" \"$DRAIN_FILE\"" in block


def test_rollback_de_enable_cobre_hooks_protecao_e_watcher():
    src = ACTIVATE.read_text(encoding="utf-8")
    assert 'HOOKS_BACKUP="$LOG_DIR/core-hooks-path.before"' in src
    assert "restore_hooks_path()" in src
    assert "HOOKS_CHANGED=1" in src
    assert src.index("PROTECTION_CHANGED=1") < src.index("branch-protection.sh --fallback")
    rollback = src[src.index("rollback_activation() {") : src.index("trap rollback_activation EXIT")]
    assert "remove_watcher" in rollback
    assert "branch-protection.sh --restore" in rollback
    assert "restore_hooks_path" in rollback


def test_scheduler_impede_execucoes_sobrepostas():
    src = ACTIVATE.read_text(encoding="utf-8")
    assert "flock" in src
    assert "flock -n '$LOCK_FILE'" in src
    assert "ExecStart=/usr/bin/flock -n $LOCK_FILE" in src


def test_hooks_path_e_preservado_exclusivamente_no_escopo_local():
    src = ACTIVATE.read_text(encoding="utf-8")
    hooks_config_lines = [
        line
        for line in src.splitlines()
        if "git config" in line and "core.hooksPath" in line
    ]
    assert hooks_config_lines
    assert all("--local" in line for line in hooks_config_lines)
    assert all("--global" not in line for line in hooks_config_lines)
    assert all("--worktree" not in line for line in hooks_config_lines)
    assert all("--file" not in line for line in hooks_config_lines)
    assert "git config --local --get core.hooksPath" in src
    assert "git config --local core.hooksPath .githooks" in src
    assert "git config --local --unset-all core.hooksPath" in src


def _remove_watcher_harness(
    tmp_path: Path, *, unit_exists: bool, include_systemctl: bool
) -> tuple[subprocess.CompletedProcess[str], Path]:
    src = ACTIVATE.read_text(encoding="utf-8")
    funcs = src[src.index("remove_cron() {") : src.index("restore_hooks_path() {")]

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "systemctl.calls"
    unit = tmp_path / "ejc-ci-fallback.service"
    if unit_exists:
        unit.write_text("[Service]\n", encoding="utf-8")

    crontab = bin_dir / "crontab"
    crontab.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    crontab.chmod(0o755)

    if include_systemctl:
        systemctl = bin_dir / "systemctl"
        systemctl.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$*\" >> {calls!s}\n"
            "case \"$*\" in\n"
            "  *is-active*|*is-enabled*) exit 1 ;;\n"
            "esac\n"
            "exit 0\n",
            encoding="utf-8",
        )
        systemctl.chmod(0o755)

    harness = tmp_path / "harness.sh"
    harness.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"UNIT={str(unit)!r}\n"
        "CRON_MARK='# EJC_CI_FALLBACK_998'\n"
        f"{funcs}\n"
        "remove_watcher\n",
        encoding="utf-8",
    )
    harness.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    result = subprocess.run(
        ["bash", str(harness)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, calls


def test_remove_watcher_sem_unit_nao_chama_disable(tmp_path: Path):
    result, calls = _remove_watcher_harness(
        tmp_path, unit_exists=False, include_systemctl=True
    )
    assert result.returncode == 0, result.stderr
    logged = calls.read_text(encoding="utf-8") if calls.exists() else ""
    assert "disable --now ejc-ci-fallback.service" not in logged


def test_remove_watcher_com_unit_e_sem_systemctl_falha_fechado(tmp_path: Path):
    result, _ = _remove_watcher_harness(
        tmp_path, unit_exists=True, include_systemctl=False
    )
    unit = tmp_path / "ejc-ci-fallback.service"
    assert unit.exists()
    assert result.returncode != 0
