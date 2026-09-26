from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "infra" / "host-automation" / "ejc-deploy-approved.sh"
DEPLOY = ROOT / "scripts" / "deploy_vps_safe.sh"


def test_wrapper_classifica_e_propaga_escopo():
    src = WRAPPER.read_text(encoding="utf-8")
    assert "classify_deploy_scope.py" in src
    assert 'DEPLOY_SCOPE="$DEPLOY_SCOPE"' in src
    assert 'if [ "$RUN_MIGRATIONS" = "0" ]' in src
    assert 'frontend|full' in src


def test_frontend_only_ocorre_depois_do_backup_e_antes_da_mutacao_de_env():
    src = DEPLOY.read_text(encoding="utf-8")
    backup = src.index('log "Backup pré-deploy concluído."')
    branch = src.index('if [ "$DEPLOY_SCOPE" = "frontend" ]; then')
    env_snapshot = src.index("ENV_ROLLBACK_FILE=", branch)
    assert backup < branch < env_snapshot


def test_frontend_only_nao_toca_backend_worker_rag_ou_env():
    src = DEPLOY.read_text(encoding="utf-8")
    start = src.index("deploy_frontend_only()")
    end = src.index('if [ "$DEPLOY_SCOPE" = "frontend" ]; then', start)
    block = src[start:end]
    assert "docker compose build frontend" in block
    assert "force-recreate frontend" in block
    assert "ejc-frontend:rollback-" in block
    assert "reparar_conhecimento_rag" not in block
    assert "ativar_backup.sh" not in block
    assert "persist_git_sha_env" not in block
    assert "force-recreate backend" not in block
    assert "force-recreate worker" not in block


def test_full_continua_com_backend_worker_backup_e_rag():
    src = DEPLOY.read_text(encoding="utf-8")
    assert 'log "Build backend e worker"' in src
    assert 'bash scripts/backup/ativar_backup.sh' in src
    assert 'python -m scripts.reparar_conhecimento_rag' in src
    assert 'force-recreate backend' in src
    assert 'force-recreate worker' in src
