from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "infra" / "host-automation" / "ejc-deploy-approved.sh"
DEPLOY = ROOT / "scripts" / "deploy_vps_safe.sh"


def test_wrapper_classifica_e_propaga_escopo():
    src = WRAPPER.read_text(encoding="utf-8")
    assert "classify_deploy_scope.py" in src
    assert 'DEPLOY_SCOPE="$DEPLOY_SCOPE"' in src
    assert 'if [ "$RUN_MIGRATIONS" = "0" ]' in src
    assert '${RUN_SEEDS:-0}" != "1"' in src
    assert "FRONTEND_DEPLOYED_SHA" in src
    assert ".frontend_deployed_sha" in src
    assert "frontend|full" in src


def test_frontend_only_ocorre_depois_do_backup_e_antes_da_mutacao_de_env():
    src = DEPLOY.read_text(encoding="utf-8")
    backup = src.index('log "Backup pré-deploy concluído."')
    branch = src.index(
        'if [ "$DEPLOY_SCOPE" = "frontend" ]; then\n  deploy_frontend_only',
        backup,
    )
    env_snapshot = src.index('ENV_ROLLBACK_FILE="$(umask', branch)
    assert backup < branch < env_snapshot


def test_frontend_only_nao_toca_backend_worker_rag_ou_env():
    src = DEPLOY.read_text(encoding="utf-8")
    start = src.index("deploy_frontend_only()")
    end = src.index(
        'if [ "$DEPLOY_SCOPE" = "frontend" ]; then\n  deploy_frontend_only',
        start,
    )
    block = src[start:end]
    assert "docker compose build frontend" in block
    assert "force-recreate frontend" in block
    assert "ejc-frontend:rollback-" in block
    assert "FRONTEND_ONLY_ROLLBACK_ARMED=1" in block
    assert ".frontend_deployed_sha" in block
    assert 'mv -f -- "$DEPLOYED_SHA_TMP"' not in block
    assert "reparar_conhecimento_rag" not in block
    assert "ativar_backup.sh" not in block
    assert "persist_git_sha_env" not in block
    assert "force-recreate backend" not in block
    assert "force-recreate worker" not in block


def test_sinal_aciona_rollback_frontend_only():
    src = DEPLOY.read_text(encoding="utf-8")
    on_exit = src[src.index("on_exit()"):src.index("trap on_exit EXIT")]
    assert 'FRONTEND_ONLY_ROLLBACK_ARMED" = "1"' in on_exit
    assert "rollback_frontend_only" in on_exit


def test_seed_ou_imagem_sem_rollback_promovem_para_full():
    src = DEPLOY.read_text(encoding="utf-8")
    assert '[ "$RUN_SEEDS" = "1" ]' in src
    assert 'DEPLOY_SCOPE="full"' in src
    assert "Imagem atual do frontend não está disponível para rollback" in src


def test_full_continua_com_backend_worker_backup_e_rag():
    src = DEPLOY.read_text(encoding="utf-8")
    assert 'log "Build backend e worker"' in src
    assert 'bash scripts/backup/ativar_backup.sh' in src
    assert 'python -m scripts.reparar_conhecimento_rag' in src
    assert 'force-recreate backend' in src
    assert 'force-recreate worker' in src


def test_wrapper_deriva_escopo_efetivo_dos_marcadores_pos_deploy():
    src = WRAPPER.read_text(encoding="utf-8")
    assert 'EFFECTIVE_SCOPE=""' in src
    assert 'DEPLOYED_AFTER=' in src
    assert 'FRONTEND_AFTER=' in src
    assert 'if [ "$DEPLOYED_AFTER" = "$TARGET_SHA" ]; then' in src
    assert 'EFFECTIVE_SCOPE="full"' in src
    assert 'elif [ "$FRONTEND_AFTER" = "$TARGET_SHA" ]; then' in src
    assert 'EFFECTIVE_SCOPE="frontend"' in src
    assert 'if [ "$EFFECTIVE_SCOPE" = "full" ]; then' in src
