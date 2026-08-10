from __future__ import annotations

from pathlib import Path


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

    # Cron é preferido quando seu daemon está comprovadamente ativo; systemd
    # de usuário só entra como fallback com linger=yes.
    select = src[
        src.index('SCHEDULER=""') : src.index('ok "scheduler persistente selecionado:')
    ]
    assert select.index("if cron_persistente") < select.index("elif systemd_user_persistente")
    assert "sem scheduler persistente" in select


def test_watcher_recebe_path_deterministico_em_cron_e_systemd():
    src = ACTIVATE.read_text(encoding="utf-8")

    assert 'WATCHER_PATH="${EJC_FALLBACK_PATH:-$PATH}"' in src
    assert 'Environment="PATH=$WATCHER_PATH"' in src
    assert "/usr/bin/env PATH='$WATCHER_PATH'" in src
    assert "PATH='$WATCHER_PATH' cd" not in src
    assert "EJC_ALLOW_PYTHON_MISMATCH=0" in src


def test_ativacao_recusa_quoting_ambiguo_do_scheduler():
    src = ACTIVATE.read_text(encoding="utf-8")

    assert "PATH contém caractere inseguro para scheduler autônomo" in src
    assert "ROOT/LOG_DIR/REPO contém caractere inseguro para scheduler autônomo" in src
    assert "*'\"'*" in src
    assert "*'\\'*" in src
    assert "*[[:space:]]*" in src
    assert "*%*" in src


def test_ativacao_exige_enable_explicito():
    src = ACTIVATE.read_text(encoding="utf-8")

    assert 'MODE="${1:-}"' in src
    assert 'uso: $0 --enable | --disable' in src
    assert 'MODE="${1:---enable}"' not in src


def test_remove_cron_tolera_filtro_vazio_com_pipefail():
    src = ACTIVATE.read_text(encoding="utf-8")
    block = src[src.index("remove_cron() {") : src.index("remove_watcher() {")]

    assert 'grep -vF "$CRON_MARK" || true' in block
    assert "crontab -" in block


def test_disable_para_watcher_antes_de_restaurar_cloud():
    src = ACTIVATE.read_text(encoding="utf-8")
    block = src[src.index('if [ "$MODE" = "--disable" ]') : src.index('[ "$MODE" = "--enable" ]')]

    assert block.index("remove_watcher") < block.index("branch-protection.sh --cloud")
    assert "restore_hooks_path" in block


def test_rollback_cobre_hooks_e_branch_protection():
    src = ACTIVATE.read_text(encoding="utf-8")

    assert 'HOOKS_BACKUP="$LOG_DIR/core-hooks-path.before"' in src
    assert "restore_hooks_path()" in src
    assert "HOOKS_CHANGED=1" in src
    assert src.index("PROTECTION_CHANGED=1") < src.index("branch-protection.sh --fallback")
    rollback = src[src.index("rollback_activation() {") : src.index("trap rollback_activation EXIT")]
    assert "remove_watcher" in rollback
    assert "branch-protection.sh --cloud" in rollback
    assert "restore_hooks_path" in rollback


def test_scheduler_impede_execucoes_sobrepostas():
    src = ACTIVATE.read_text(encoding="utf-8")

    assert "git gh jq python3 node npm psql flock" in src
    assert "flock -n '$LOCK_FILE'" in src
    assert "ExecStart=/usr/bin/flock -n $LOCK_FILE" in src


def test_hooks_path_e_preservado_exclusivamente_no_escopo_local():
    src = ACTIVATE.read_text(encoding="utf-8")

    # Leitura, gravação e restauração devem usar --local. Assim, se houver apenas
    # core.hooksPath global, a ativação registra __UNSET__ e a desativação remove
    # somente o override local, sem copiar o valor global para .git/config.
    assert "git config --local --get core.hooksPath" in src
    assert "git config --local core.hooksPath .githooks" in src
    assert "git config --local --unset-all core.hooksPath" in src
    restore = src[src.index("restore_hooks_path() {") : src.index('if [ "$MODE" = "--disable" ]')]
    assert "git config --local core.hooksPath" in restore
    assert "git config core.hooksPath" not in restore


def test_remove_watcher_nao_falha_quando_unit_nunca_foi_instalada():
    src = ACTIVATE.read_text(encoding="utf-8")
    block = src[src.index("remove_watcher() {") : src.index("restore_hooks_path() {")]

    assert 'unit_aplicavel=0' in block
    assert '[ -f "$UNIT" ]' in block
    assert "systemctl --user is-active --quiet ejc-ci-fallback.service" in block
    assert "systemctl --user is-enabled --quiet ejc-ci-fallback.service" in block
    assert 'if [ "$unit_aplicavel" -eq 1 ]; then' in block
    # O disable não pode ser executado de forma incondicional antes do teste.
    assert block.index('if [ "$unit_aplicavel" -eq 1 ]; then') < block.index(
        "systemctl --user disable --now ejc-ci-fallback.service"
    )
