"""Contrato de segurança do rollout de ativação do gate de vigência."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVATE = ROOT / ".github" / "workflows" / "rag-vigencia-activate.yml"
DEPLOY = ROOT / ".github" / "workflows" / "deploy-vps.yml"
PREARM = ROOT / ".github" / "workflows" / "rag-vigencia-prearm.yml"


def test_ativacao_compartilha_lock_repository_wide_com_deploy_e_prearm():
    activate = ACTIVATE.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")
    prearm = PREARM.read_text(encoding="utf-8")

    assert "group: deploy-vps" in deploy
    assert "group: deploy-vps" in prearm
    assert "group: deploy-vps" in activate
    assert "group: rag-vigencia-activate" not in activate
    assert "cancel-in-progress: false" in activate


def test_ativacao_exige_sha_prearm_e_flag_false_antes_do_backfill():
    texto = ACTIVATE.read_text(encoding="utf-8")

    assert 'deployed="$(sudo cat "$APP_DIR/.deployed_sha"' in texto
    assert 'if ! sudo test -f "$prearm"; then' in texto
    assert "RAG_EXIGIR_VIGENCIA_VERIFICADA=false" in texto
    assert "--incluir-legislacao --forcar-legislacao" in texto


def test_ativacao_tem_flip_atomico_prova_e_rollback():
    texto = ACTIVATE.read_text(encoding="utf-8")

    assert 'sudo mv -f "$candidate" "$env_file"' in texto
    assert 'sudo cp -p "$env_file" "$backup"' in texto
    assert 'sudo chmod 600 "$backup"' in texto
    assert "final_value=" in texto
    assert "rollback_flag()" in texto
    assert "set_flag false" in texto
    assert "set_flag true" in texto
