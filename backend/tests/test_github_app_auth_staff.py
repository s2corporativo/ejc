from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "scripts" / "github-app-auth.sh"


def _run_validation(path: Path) -> subprocess.CompletedProcess[str]:
    script = (
        f"source {AUTH!s}; "
        'EJC_FALLBACK_APP_PRIVATE_KEY_FILE="$1"; '
        "_ejc_validate_private_key >/dev/null"
    )
    return subprocess.run(
        ["bash", "-c", script, "_", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_private_key_rejeita_permissao_de_grupo_ou_outros(tmp_path: Path):
    key = tmp_path / "app.pem"
    key.write_text("dummy\n", encoding="utf-8")
    key.chmod(0o644)
    assert _run_validation(key).returncode != 0


def test_private_key_owner_only_e_aceita_sem_expor_conteudo(tmp_path: Path):
    key = tmp_path / "app.pem"
    secret = "PRIVATE-KEY-MATERIAL-NAO-LOGAR"
    key.write_text(secret, encoding="utf-8")
    key.chmod(0o600)
    result = _run_validation(key)
    assert result.returncode == 0
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_auth_usa_token_efemero_escopado_e_nao_persiste_credencial():
    src = AUTH.read_text(encoding="utf-8")
    assert "access_tokens" in src
    assert "_EJC_APP_TOKEN_REFRESH_SECONDS" in src
    assert 'GH_TOKEN="$_EJC_APP_TOKEN" gh api' in src
    assert "curl --config -" in src
    assert "permissions:{checks:\"write\"}" in src
    assert "repositories:[$repo]" in src
    assert "shopt -s lastpipe" in src
    assert "write_text" not in src

    # O GitHub alterou o formato de installation tokens em 2026. O contrato
    # local valida tipo/comprimento mínimo apenas para rejeitar resposta vazia,
    # sem assumir o formato legado de 40 caracteres.
    assert 'length > 20' in src
    assert 'length == 40' not in src
    assert 'length != 40' not in src
