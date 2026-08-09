"""Contrato de segurança do pré-armamento do gate de vigência em produção.

O pré-armamento é uma etapa do próprio Deploy VPS: não cria uma segunda corrida
no grupo de concorrência e usa o mesmo TARGET_SHA efetivamente implantado.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[2]
FLUXO_DEPLOY = RAIZ / ".github" / "workflows" / "deploy-vps.yml"
FLUXO_PREARM_SEPARADO = RAIZ / ".github" / "workflows" / "rag-vigencia-prearm.yml"


def _texto() -> str:
    return FLUXO_DEPLOY.read_text(encoding="utf-8")


def _trecho_prearm() -> str:
    texto = _texto()
    inicio = texto.index("      - name: Pré-armar gate de vigência em modo compatível")
    fim = texto.index("\n      - name: Resumo da implantação", inicio)
    return texto[inicio:fim]


def _trecho_gate_sha() -> str:
    """Extrai a verificação real de SHA do passo de pré-armamento."""
    trecho = _trecho_prearm()
    inicio = trecho.index('          deployed="$(sudo cat')
    fim = trecho.index("\n\n          sudo mkdir -p", inicio)
    gate = textwrap.dedent(trecho[inicio:fim])
    # O teste roda sem sudo em diretório temporário, preservando a lógica real.
    return gate.replace('sudo cat "$APP_DIR/.deployed_sha"', 'cat "$APP_DIR/.deployed_sha"')


def test_prearm_fica_dentro_do_deploy_e_nao_cria_workflow_concorrente():
    texto = _texto()
    assert not FLUXO_PREARM_SEPARADO.exists()
    assert texto.count("group: deploy-vps") == 1
    assert "group: rag-vigencia-prearm" not in texto
    assert "- name: Smoke test pós-deploy" in texto
    assert texto.index("- name: Smoke test pós-deploy") < texto.index(
        "- name: Pré-armar gate de vigência em modo compatível"
    )


def test_env_nao_e_sobrescrito_in_place():
    trecho = _trecho_prearm()
    assert 'sudo install -o "$uid" -g "$gid" -m "$mode" "$work" "$candidate"' in trecho
    assert 'sudo mv -f "$candidate" "$env_file"' in trecho
    assert 'sudo install -o "$uid" -g "$gid" -m "$mode" "$work" "$env_file"' not in trecho


def test_rollback_tem_copia_0600_e_restore_atomico():
    trecho = _trecho_prearm()
    assert 'sudo cp -p "$env_file" "$backup"' in trecho
    assert 'sudo chmod 600 "$backup"' in trecho
    assert 'sudo mv -f "$backup" "$env_file"' in trecho
    assert 'if [ "$concluido" != "1" ]; then' in trecho
    assert 'if [ "$alterado" = "1" ] && sudo test -f "$backup"; then' in trecho


def test_saida_e_sinais_passam_pelo_rollback_quando_necessario():
    trecho = _trecho_prearm()
    assert "trap finalizar EXIT" in trecho
    assert "trap 'exit 130' INT" in trecho
    assert "trap 'exit 143' TERM" in trecho
    assert "trap - EXIT INT TERM" in trecho
    indice_restore = trecho.index('sudo mv -f "$backup" "$env_file"')
    indice_concluido = trecho.index('if [ "$concluido" != "1" ]; then')
    assert indice_concluido < indice_restore


def test_transformacao_deduplica_chave_e_prova_candidato():
    trecho = _trecho_prearm()
    assert 'BEGIN { seen = 0 }' in trecho
    assert 'if (!seen)' in trecho
    assert 'candidate_total=' in trecho
    assert 'candidate_false=' in trecho
    assert 'final_total=' in trecho
    assert 'final_false=' in trecho


def test_marcador_so_nasce_depois_da_validacao_final_quando_ha_alteracao():
    trecho = _trecho_prearm()
    indice_final = trecho.rindex('final_false=')
    indice_marcador = trecho.rindex('sudo tee "$marker"')
    indice_concluido = trecho.rindex("concluido=1")
    assert indice_final < indice_marcador < indice_concluido


def test_fast_path_revalida_env_remove_backup_e_atualiza_prova_antes_de_sair():
    trecho = _trecho_prearm()
    inicio = trecho.index('total="$(sudo grep -c')
    indice_false = trecho.index('false_count="$(sudo grep -c', inicio)
    indice_remocao = trecho.index('sudo rm -f "$backup"', indice_false)
    indice_marcador = trecho.index('sudo tee "$marker"', indice_remocao)
    indice_concluido = trecho.index("concluido=1", indice_marcador)
    indice_saida = trecho.index("exit 0", indice_concluido)
    assert inicio < indice_false < indice_remocao < indice_marcador < indice_concluido < indice_saida


def test_gate_sha_falha_se_deployed_sha_diverge_e_aceita_sha_igual(tmp_path: Path):
    gate = _trecho_gate_sha()
    sha_esperado = "a" * 40
    arquivo_sha = tmp_path / ".deployed_sha"
    ambiente = {**os.environ, "APP_DIR": str(tmp_path), "TARGET_SHA": sha_esperado}

    arquivo_sha.write_text("b" * 40 + "\n", encoding="utf-8")
    divergente = subprocess.run(
        ["bash", "-c", f"set -euo pipefail\n{gate}"],
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )
    assert divergente.returncode != 0
    assert "não comprova o TARGET_SHA" in divergente.stdout

    arquivo_sha.write_text(sha_esperado + "\n", encoding="utf-8")
    correspondente = subprocess.run(
        ["bash", "-c", f"set -euo pipefail\n{gate}"],
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )
    assert correspondente.returncode == 0


def test_prearm_usa_o_mesmo_target_sha_registrado_pelo_deploy():
    texto = _texto()
    indice_registro = texto.index('printf \'%s\\n\' "$TARGET_SHA" | sudo tee /opt/ejc/.deployed_sha')
    indice_prearm = texto.index("- name: Pré-armar gate de vigência em modo compatível")
    trecho = _trecho_prearm()
    assert indice_registro < indice_prearm
    assert 'deployed" != "$TARGET_SHA"' in trecho
    assert 'printf \'%s\\n\' "$TARGET_SHA" | sudo tee "$marker"' in trecho


def test_deploy_futuro_nao_rebaixa_gate_ja_ativado():
    trecho = _trecho_prearm()
    indice_ativado = trecho.index('if sudo test -f "$activated_marker"; then')
    indice_true = trecho.index("true_count=", indice_ativado)
    indice_concluido = trecho.index("concluido=1", indice_true)
    indice_saida = trecho.index("exit 0", indice_concluido)
    indice_awk = trecho.index("sudo cat \"$env_file\" | awk")
    assert indice_ativado < indice_true < indice_concluido < indice_saida < indice_awk
    assert "marcador de ativação existe, mas .env não está canonicamente true" in trecho


def test_prearm_nao_executa_operacoes_de_banco_container_ou_exposicao_de_env():
    trecho = _trecho_prearm()
    proibidos = (
        "docker ",
        "docker-compose",
        "docker compose",
        "alembic ",
        "psql ",
        "restart ",
        "systemctl ",
        "printenv",
        "env |",
        'echo "$env_file"',
        'cat "$env_file"\n',
    )
    for comando in proibidos:
        assert comando not in trecho, f"prearm ganhou operação fora do escopo: {comando}"

    # A leitura do .env existe apenas como entrada de uma transformação cujo
    # stdout é redirecionado ao arquivo temporário; o conteúdo nunca é logado.
    assert 'sudo cat "$env_file" | awk' in trecho
    assert "' > \"$work\"" in trecho
    assert trecho.count("RAG_EXIGIR_VIGENCIA_VERIFICADA=false") >= 3
