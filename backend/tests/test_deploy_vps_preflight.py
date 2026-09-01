"""Regressões de segurança e observabilidade do workflow de deploy da VPS."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-vps.yml"
TX_SCRIPT = ROOT / "scripts" / "deploy_workflow_transaction.sh"
LOCK_SCRIPT = ROOT / "scripts" / "deploy_lock.sh"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_vps_safe.sh"


def _texto() -> str:
    # Skip CIRÚRGICO, não do módulo: o Actions foi arquivado em 31/08
    # (`b77ff4c`), mas o deploy real nunca morou nele — mora nos scripts, que
    # este arquivo também testa. Adormecer só quem lê o YAML mantém vivas as
    # garantias que ainda têm objeto (lock, SHA implantado, travas do manual).
    if not WORKFLOW.is_file():
        pytest.skip("GitHub Actions arquivado em 31/08 (b77ff4c) — workflows movidos para docs/arquivo/ci/github-actions-legacy/; Woodpecker é o CI oficial")
    return WORKFLOW.read_text(encoding="utf-8")


def test_preflight_nao_confia_globalmente_no_git_do_runner():
    texto = _texto()
    assert 'stat -c %u "$GITHUB_WORKSPACE"' in texto
    assert 'git -c safe.directory="$GITHUB_WORKSPACE" rev-parse HEAD' in texto
    assert "git config --global" not in texto
    assert "safe.directory=*" not in texto


def test_preflight_nomeia_falhas_e_valida_dependencias_do_mutex():
    texto = _texto()
    assert "set +e" in texto
    assert "::error::Pré-voo do deploy:" in texto
    for marcador in (
        "/opt/ejc",
        "/opt/ejc/.env",
        "ejc_db",
        "python3",
        "rsync",
        "flock",
        "sudo",
        "deploy_lock.sh",
        "deploy_workflow_transaction.sh",
    ):
        assert marcador in texto
    assert "sudo -n true" in texto


def test_env_de_producao_permanece_proprietario_root_0600_sem_exigir_leitura_do_runner():
    tx = TX_SCRIPT.read_text(encoding="utf-8")
    assert tx.count('sudo -n test -r "$APP_DIR/.env"') == 2
    assert tx.count("sudo -n stat -c '%u:%g:%a' \"$APP_DIR/.env\"") == 2
    assert tx.count('= "0:0:600"') == 2
    assert "root:root em modo 0600 antes do deploy" in tx
    assert "root:root em modo 0600 após o rsync" in tx
    assert '[ -r "$APP_DIR/.env" ]' not in tx
    assert 'sudo -n chown' not in tx
    assert 'sudo -n chmod 600 "$APP_DIR/.env"' not in tx
    assert "chmod 644" not in "\n".join(
        line for line in tx.splitlines() if ".env" in line
    )
    assert "chmod 666" not in tx
    assert "chmod 777" not in tx


def test_sync_e_deploy_compartilham_um_unico_fd_de_lock():
    workflow = _texto()
    tx = TX_SCRIPT.read_text(encoding="utf-8")
    lock = LOCK_SCRIPT.read_text(encoding="utf-8")
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "run: bash scripts/deploy_workflow_transaction.sh" in workflow
    assert "ejc_deploy_lock_acquire_production" in tx
    assert 'EJC_DEPLOY_LOCK_FD=9' in lock
    assert 'export EJC_DEPLOY_LOCK_FD' in lock
    assert 'bash scripts/deploy_vps_safe.sh' in tx
    assert 'source "$SCRIPT_DIR/deploy_lock.sh"' in deploy
    assert 'ejc_deploy_lock_acquire "$APP_DIR"' in deploy
    assert "ejc_deploy_lock_acquire_production" in lock

    assert 'EJC_DEPLOY_PRODUCTION_LOCK_ROOT="/run/lock/ejc"' in lock
    assert "XDG_RUNTIME_DIR" not in lock
    assert "${HOME" not in lock
    assert "install -d -m 0750 -o root -g" in lock
    assert "-m 0660 -o root -g" in lock
    assert "stat -Lc '%d:%i'" in lock
    assert "inode mudou durante abertura" in lock
    assert "EJC_DEPLOY_LOCK_ROOT:-" not in lock


def test_resumo_distingue_fases_sem_confiar_no_outcome_ambiguo_do_step():
    texto = _texto()
    assert "id: sync" in texto
    assert "SYNC_OUTCOME" not in texto
    for estado in ("pre_sync", "sync_started", "sync_completed", "deploy_completed"):
        assert estado in texto
    assert "abortado antes de tocar produção" in texto
    assert "FALHOU APÓS TOCAR PRODUÇÃO" in texto
    assert "ESTADO INCERTO" in texto
    assert "ESTADO DESCONHECIDO" in texto
    assert "GITHUB_RUN_ID" in texto
    assert "GITHUB_RUN_ATTEMPT" in texto


def test_prearm_mutavel_reutiliza_mesmo_mutex_e_confere_sha_implantado():
    texto = _texto()
    prearm = texto[
        texto.index("- name: Pré-armar gate de vigência") : texto.index(
            "- name: Resumo da implantação"
        )
    ]
    assert 'source "$APP_DIR/scripts/deploy_lock.sh"' in prearm
    assert "ejc_deploy_lock_acquire" in prearm
    assert 'deployed="$(sudo cat "$APP_DIR/.deployed_sha"' in prearm
    assert 'deployed" != "$TARGET_SHA"' in prearm


def test_registro_de_sha_acontece_dentro_do_executor_bloqueado():
    workflow = _texto()
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "Registrar versão implantada" not in workflow
    assert 'DEPLOYED_SHA_TMP="$APP_DIR/.deployed_sha.new.$$"' in deploy
    assert 'mv -f -- "$DEPLOYED_SHA_TMP" "$APP_DIR/.deployed_sha"' in deploy
    assert deploy.index("ejc_deploy_lock_acquire") < deploy.index("DEPLOYED_SHA_TMP=")


def test_backup_default_e_validado_antes_das_mutacoes_do_executor():
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    backup = deploy.index('BACKUP_SAIDA=""')
    snapshot = deploy.index('mktemp /tmp/ejc-env-rollback')
    migrador = deploy.index('migrar_env_obsoletos.sh .env --backup-path')
    inspect = deploy.index("docker inspect -f '{{.Image}}'")
    tag = deploy.index('OLD_BACKEND_TAG="ejc-backend:rollback-')
    build = deploy.index('log "Build frontend"')
    assert backup < snapshot < migrador < inspect < tag < build
    assert 'REQUIRE_PREDEPLOY_BACKUP="${REQUIRE_PREDEPLOY_BACKUP:-1}"' in deploy


def test_deploy_automatico_so_aceita_ci_da_main():
    texto = _texto()
    assert 'branches: [main]' in texto
    assert "github.ref_name == 'main'" in texto
    assert "github.event.workflow_run.conclusion == 'success'" in texto
