from __future__ import annotations

import subprocess
from pathlib import Path


RAIZ_PROJETO = Path(__file__).resolve().parents[2]
SCRIPT_AUTENTICACAO = RAIZ_PROJETO / "scripts" / "github-app-auth.sh"


def _executar_validacao(caminho_chave: Path) -> subprocess.CompletedProcess[str]:
    script = (
        'CAMINHO_AUTH="$1"; '
        f"source {SCRIPT_AUTENTICACAO!s}; "
        'EJC_FALLBACK_APP_PRIVATE_KEY_FILE="$CAMINHO_AUTH"; '
        "_ejc_validate_private_key >/dev/null"
    )
    return subprocess.run(
        ["bash", "-c", script, "--", str(caminho_chave)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_private_key_rejeita_permissao_de_grupo_ou_outros(tmp_path: Path):
    chave = tmp_path / "app.pem"
    chave.write_text("dummy\n", encoding="utf-8")
    chave.chmod(0o644)
    assert _executar_validacao(chave).returncode != 0


def test_private_key_owner_only_e_aceita_sem_expor_conteudo(tmp_path: Path):
    chave = tmp_path / "app.pem"
    segredo = "PRIVATE-KEY-MATERIAL-NAO-LOGAR"
    chave.write_text(segredo, encoding="utf-8")
    chave.chmod(0o600)
    resultado = _executar_validacao(chave)
    assert resultado.returncode == 0
    assert segredo not in resultado.stdout
    assert segredo not in resultado.stderr


def test_auth_usa_token_efemero_escopado_e_nao_persiste_credencial():
    conteudo_script = SCRIPT_AUTENTICACAO.read_text(encoding="utf-8")
    assert "access_tokens" in conteudo_script
    assert "_EJC_APP_TOKEN_REFRESH_SECONDS" in conteudo_script
    assert 'GH_TOKEN="$_EJC_APP_TOKEN" gh api' in conteudo_script
    assert "curl -q --config -" in conteudo_script
    assert "permissions:{checks:\"write\"}" in conteudo_script
    assert "repositories:[$repo]" in conteudo_script
    assert "shopt -s lastpipe" in conteudo_script
    assert "write_text" not in conteudo_script

    # O GitHub alterou o formato de installation tokens em 2026. O contrato
    # local valida tipo/comprimento mínimo apenas para rejeitar resposta vazia,
    # sem assumir o formato legado de 40 caracteres.
    assert 'length > 20' in conteudo_script
    assert 'length == 40' not in conteudo_script
    assert 'length != 40' not in conteudo_script
