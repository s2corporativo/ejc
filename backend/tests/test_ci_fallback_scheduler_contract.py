from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVATE = ROOT / "scripts" / "ci-fallback-activate.sh"


def _source() -> str:
    return ACTIVATE.read_text(encoding="utf-8")


def test_scheduler_autonomo_exige_persistencia_comprovada():
    src = _source()
    assert "cron_persistente()" in src
    assert "pgrep -x cron" in src
    assert "pgrep -x crond" in src
    assert "systemd_user_persistente()" in src
    assert "loginctl show-user" in src
    assert '-p Linger --value' in src
    assert '= "yes" ]' in src

    selection = src[
        src.index('SCHEDULER=""') : src.index('ok "scheduler persistente selecionado:')
    ]
    assert selection.index("if cron_persistente") < selection.index(
        "elif systemd_user_persistente"
    )
    assert "sem scheduler persistente" in selection


def test_scheduler_propaga_apenas_caminhos_e_identidades_operacionais():
    src = _source()
    assert 'WATCHER_PATH="${EJC_FALLBACK_PATH:-$PATH}"' in src
    assert 'Environment="PATH=$WATCHER_PATH"' in src
    assert "/usr/bin/env PATH='$WATCHER_PATH'" in src
    assert "EJC_FALLBACK_APP_ID" in src
    assert "EJC_FALLBACK_INSTALLATION_ID" in src
    assert "EJC_FALLBACK_APP_PRIVATE_KEY_FILE" in src
    assert "EJC_CI_WORKER_USER" in src
    assert "EJC_CI_WORKER_ROOT" in src
    assert "GH_TOKEN=" not in src
    assert "GITHUB_TOKEN=" not in src


def test_worker_e_validado_antes_de_qualquer_mutacao_de_branch_protection():
    src = _source()
    preflight = src.index("bash scripts/ci-worker-isolation.sh preflight")
    journal = src.index('journal_begin "$SCHEDULER"')
    protection = src.index("branch-protection.sh --fallback")
    assert preflight < journal < protection
    assert "worker dedicado não atende aos invariantes de isolamento" in src


def test_ativacao_exige_modo_explicito_e_recusa_quoting_ambiguo():
    src = _source()
    assert 'MODE="${1:-}"' in src
    assert 'uso: $0 --enable | --disable | --status' in src
    assert 'MODE="${1:---enable}"' not in src
    assert 'if [ "$MODE" = "--status" ]' in src
    assert "caractere inseguro para scheduler" in src
    assert "*'\"'*" in src
    assert "*'\\'*" in src
    assert "*%*" in src


def test_journal_e_drain_tornam_enable_e_disable_recuperaveis():
    src = _source()
    assert 'JOURNAL_FILE="$LOG_DIR/activation-transaction.json"' in src
    assert "recover_incomplete_transaction()" in src
    assert "create_drain_marker" in src
    assert "journal_phase draining" in src
    assert "journal_phase watcher" in src
    assert "journal_phase hooks" in src
    assert "journal_phase protection" in src
    assert "journal_phase commit" in src
    assert "journal_phase active" in src


def test_disable_restaura_protecao_antes_de_remover_produtor():
    src = _source()
    block = src[
        src.index('if [ "$MODE" = "--disable" ]') : src.index(
            '[ "$MODE" = "--enable" ]'
        )
    ]
    assert "flock -w 120 8" in block
    assert "branch-protection.sh --restore" in block
    assert "remove_watcher" in block
    assert block.index("branch-protection.sh --restore") < block.index("remove_watcher")
    assert "journal/drain/watcher preservados" in block


def test_enable_instala_produtor_drenado_antes_de_aplicar_required_check():
    src = _source()
    mutation = src[src.index('journal_begin "$SCHEDULER"') :]
    assert mutation.index("create_drain_marker") < mutation.index("install_watcher")
    assert mutation.index("install_watcher") < mutation.index(
        "branch-protection.sh --fallback"
    )
    assert mutation.index("branch-protection.sh --fallback") < mutation.index(
        'rm -f "$DRAIN_FILE"'
    )


def test_scheduler_impede_execucoes_sobrepostas():
    src = _source()
    assert "ExecStart=/usr/bin/flock -n $LOCK_FILE" in src
    assert "flock -n '$LOCK_FILE'" in src


def test_hooks_path_e_exclusivamente_local():
    src = _source()
    hook_lines = [
        line for line in src.splitlines() if "git config" in line and "core.hooksPath" in line
    ]
    assert hook_lines
    assert all("--local" in line for line in hook_lines)
    assert all("--global" not in line for line in hook_lines)
    assert "git config --local --get core.hooksPath" in src
    assert "git config --local core.hooksPath .githooks" in src
    assert "git config --local --unset-all core.hooksPath" in src


def test_active_state_registra_worker_e_state_root_para_diagnostico():
    src = _source()
    assert '--arg worker_user "$WORKER_USER"' in src
    assert '--arg worker_root "$WORKER_ROOT"' in src
    assert '--arg state_root "$CACHE_ROOT"' in src
    assert "worker_user:$worker_user" in src
    assert "worker_root:$worker_root" in src
    assert "state_root:$state_root" in src
