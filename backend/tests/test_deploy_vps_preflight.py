"""Regressões de segurança e observabilidade do workflow de deploy da VPS."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-vps.yml"


def _texto() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_preflight_nao_confia_globalmente_no_git_do_runner():
    texto = _texto()
    assert 'stat -c %u "$GITHUB_WORKSPACE"' in texto
    assert 'git -c safe.directory="$GITHUB_WORKSPACE" rev-parse HEAD' in texto
    assert "git config --global" not in texto
    assert "safe.directory=*" not in texto


def test_preflight_nomeia_falhas_e_nao_aborta_mudo():
    texto = _texto()
    assert "set +e" in texto
    assert "::error::Pré-voo do deploy:" in texto
    for marcador in (
        "/opt/ejc",
        "/opt/ejc/.env",
        "ejc_db",
        "python3",
        "rsync",
    ):
        assert marcador in texto


def test_env_de_producao_nao_e_world_readable():
    texto = _texto()
    assert "sudo chmod 600 /opt/ejc/.env" in texto
    assert "sudo chown" in texto and "/opt/ejc/.env" in texto
    assert "chmod 644 /opt/ejc/.env" not in texto
    assert "chmod 666 /opt/ejc/.env" not in texto
    assert "chmod 777 /opt/ejc/.env" not in texto


def test_resumo_distingue_falha_antes_e_depois_de_tocar_producao():
    texto = _texto()
    assert "id: sync" in texto
    assert "SYNC_OUTCOME: ${{ steps.sync.outcome }}" in texto
    assert "abortado antes de tocar produção" in texto
    assert "FALHOU APÓS TOCAR PRODUÇÃO" in texto
    assert "ESTADO INCERTO" in texto


def test_deploy_automatico_so_aceita_ci_da_main():
    texto = _texto()
    assert 'branches: [main]' in texto
    assert "github.ref_name == 'main'" in texto
    assert "github.event.workflow_run.conclusion == 'success'" in texto
