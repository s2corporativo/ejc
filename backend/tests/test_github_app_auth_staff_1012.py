from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "scripts" / "github-app-auth.sh"


def test_installation_token_e_renovado_sem_persistencia_externa(tmp_path: Path):
    counter = tmp_path / "mint-count"
    counter.write_text("0\n", encoding="utf-8")
    script = f"""
source {AUTH}
COUNT_FILE="$1"
_ejc_mint_installation_token() {{
  count="$(cat "$COUNT_FILE")"
  count=$((count + 1))
  printf '%s\n' "$count" > "$COUNT_FILE"
  printf 'token-%s-abcdefghijklmnopqrstuvwxyz0123456789\n' "$count"
}}
ejc_github_app_refresh
first="$_EJC_APP_TOKEN"
ejc_github_app_refresh
second="$_EJC_APP_TOKEN"
[ "$first" = "$second" ] || exit 21
[ "$(cat "$COUNT_FILE")" -eq 1 ] || exit 22
_EJC_APP_TOKEN_ISSUED_AT=$(( $(date +%s) - _EJC_APP_TOKEN_REFRESH_SECONDS - 1 ))
ejc_github_app_refresh
third="$_EJC_APP_TOKEN"
[ "$third" != "$second" ] || exit 23
[ "$(cat "$COUNT_FILE")" -eq 2 ] || exit 24
ejc_github_app_clear
[ -z "$_EJC_APP_TOKEN" ] || exit 25
[ "$_EJC_APP_TOKEN_ISSUED_AT" -eq 0 ] || exit 26
"""
    proc = subprocess.run(
        ["bash", "-c", script, "_", str(counter)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_mint_restringe_token_ao_repo_e_checks_write():
    source = AUTH.read_text(encoding="utf-8")
    mint = source[
        source.index("_ejc_mint_installation_token() {") : source.index(
            "ejc_github_app_refresh() {"
        )
    ]
    assert 'repo_name="${repo#*/}"' in mint
    assert "repositories:[$repo]" in mint
    assert 'permissions:{checks:"write"}' in mint
    assert 'contents:"write"' not in mint
    assert 'pull_requests:"write"' not in mint
    assert 'administration:"write"' not in mint


def test_chave_privada_nunca_pode_ficar_no_repo_producao_ou_grupo():
    source = AUTH.read_text(encoding="utf-8")
    validate = source[
        source.index("_ejc_validate_private_key() {") : source.index(
            "_ejc_validate_app_config() {"
        )
    ]
    assert "/opt/ejc" in validate
    assert '"$root"|"$root"/*' in validate
    assert "stat -c %u" in validate
    assert "(perm & 0077) == 0" in validate
    assert '[ ! -L "$key" ]' in validate


def test_jwt_e_curto_e_assinado_com_rs256():
    source = AUTH.read_text(encoding="utf-8")
    mint = source[
        source.index("_ejc_mint_installation_token() {") : source.index(
            "ejc_github_app_refresh() {"
        )
    ]
    assert '{"alg":"RS256","typ":"JWT"}' in mint
    assert "iat=$((now - 60))" in mint
    assert "exp=$((now + 540))" in mint
    assert 'openssl dgst -sha256 -sign "$key" -binary' in mint
    assert "Authorization: Bearer %s" in mint
