"""Contrato de segurança do prearm do gate de vigência em produção."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "rag-vigencia-prearm.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-vps.yml"


def _texto() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_env_nao_e_sobrescrito_in_place():
    texto = _texto()
    assert 'sudo install -o "$uid" -g "$gid" -m "$mode" "$work" "$candidate"' in texto
    assert 'sudo mv -f "$candidate" "$env_file"' in texto
    assert 'sudo install -o "$uid" -g "$gid" -m "$mode" "$work" "$env_file"' not in texto


def test_rollback_tem_copia_0600_e_restore_atomico():
    texto = _texto()
    assert 'sudo cp -p "$env_file" "$backup"' in texto
    assert 'sudo chmod 600 "$backup"' in texto
    assert 'sudo mv -f "$backup" "$env_file"' in texto


def test_transformacao_deduplica_chave_e_prova_candidato():
    texto = _texto()
    assert 'BEGIN { seen = 0 }' in texto
    assert 'if (!seen)' in texto
    assert 'candidate_total=' in texto
    assert 'candidate_false=' in texto
    assert 'final_total=' in texto
    assert 'final_false=' in texto


def test_marcador_so_nasce_depois_da_validacao_final():
    texto = _texto()
    i_final = texto.index('final_false=')
    i_marker = texto.index('sudo tee "$marker"')
    assert i_final < i_marker


def test_fast_path_revalida_o_env_real():
    texto = _texto()
    i_marker_check = texto.index('if sudo test -f "$marker"; then')
    i_total = texto.index('total="$(sudo grep -c', i_marker_check)
    i_false = texto.index('false_count="$(sudo grep -c', i_marker_check)
    i_exit = texto.index('exit 0', i_marker_check)
    assert i_marker_check < i_total < i_exit
    assert i_marker_check < i_false < i_exit


def test_prearm_compartilha_lock_com_deploy_vps():
    prearm = _texto()
    deploy = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "group: deploy-vps" in deploy
    assert "group: deploy-vps" in prearm
    assert "group: rag-vigencia-prearm" not in prearm
    assert "cancel-in-progress: false" in prearm
