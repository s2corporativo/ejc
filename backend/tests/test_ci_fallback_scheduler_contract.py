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
    assert '] = "yes"' in src

    # Cron é preferido quando seu daemon está comprovadamente ativo; systemd
    # de usuário só entra como fallback com linger=yes.
    select = src[src.index('SCHEDULER=""') : src.index("# Prova mínima do executor")]
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
    assert "*[[:space:]]*" in src
    assert "*%*" in src
