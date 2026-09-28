"""Contrato: código de PR nunca executa na VPS de produção."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"


def _workflows() -> list[Path]:
    assert WF.is_dir(), "diretório de workflows ativo ausente"
    return sorted(p for p in WF.iterdir() if p.suffix in {".yml", ".yaml"})


def test_ci_pr_usa_runner_github_hosted():
    texto = (WF / "ci.yml").read_text(encoding="utf-8")
    assert "pull_request:" in texto
    assert "runs-on: ubuntu-latest" in texto
    assert "runs-on: [self-hosted, ejc-vps]" not in texto
    assert "ejc-vps" not in texto


def test_nenhum_workflow_de_pr_expoe_runner_self_hosted():
    for path in _workflows():
        texto = path.read_text(encoding="utf-8")
        if "pull_request:" not in texto:
            continue
        assert "runs-on: [self-hosted" not in texto, (
            f"{path.name} expõe Pull Request a runner self-hosted"
        )
        assert "ejc-vps" not in texto, (
            f"{path.name} referencia runner produtivo em workflow acessível por PR"
        )


def test_ci_nao_recebe_segredos_de_producao():
    texto = (WF / "ci.yml").read_text(encoding="utf-8")
    proibidos = (
        "PRODUCTION_SSH",
        "VPS_SSH",
        "POSTGRES_PASSWORD_PRODUCTION",
        "PII_ENCRYPTION_KEY_PRODUCTION",
        "secrets.PRODUCTION",
    )
    for item in proibidos:
        assert item not in texto, f"CI de PR referencia segredo de produção: {item}"


def test_deploy_nao_e_executado_no_ci_de_pr():
    texto = (WF / "ci.yml").read_text(encoding="utf-8")
    assert "Coolify" in texto
    assert "docker compose up -d" not in texto
    assert "deploy_vps_safe.sh --" not in texto
