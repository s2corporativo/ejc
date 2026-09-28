"""Contrato de governança da esteira GitHub Actions + Coolify."""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
GOV_DOC = REPO_ROOT / "docs" / "GOVERNANCA_IA.md"


def _texto(path: Path) -> str:
    assert path.is_file(), f"arquivo obrigatório ausente: {path.relative_to(REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_actions_e_o_gate_canonico():
    texto = _texto(CI_PATH)
    assert "CI canônico do EJC em runners GitHub-hosted" in texto
    assert "pull_request:" in texto
    assert "branches: [main]" in texto
    assert "EJC Gate — Actions" in texto


def test_pr_nunca_roda_na_vps_de_producao():
    texto = _texto(CI_PATH)
    assert "runs-on: ubuntu-latest" in texto
    assert "self-hosted" not in texto
    assert "ejc-vps" not in texto


def test_backend_tem_gates_minimos():
    texto = _texto(CI_PATH)
    for comando in (
        "python -m ruff check app",
        "python -m alembic heads",
        "python -m alembic upgrade head",
        "pytest tests -q",
    ):
        assert comando in texto, f"gate backend ausente: {comando}"


def test_frontend_tem_gates_minimos():
    texto = _texto(CI_PATH)
    for comando in (
        "npm ci --prefer-offline",
        "npm run lint",
        "npm test",
        "npm run build",
    ):
        assert comando in texto, f"gate frontend ausente: {comando}"


def test_pipeline_usa_banco_descartavel_pgvector():
    texto = _texto(CI_PATH)
    assert "pgvector/pgvector:pg16" in texto
    assert "POSTGRES_DB=ejc_db" in texto
    assert "DATABASE_URL:" in texto
    assert "localhost:55432/ejc_db" in texto


def test_seguranca_profunda_permanece_bloqueante():
    texto = _texto(CI_PATH)
    assert "gitleaks/gitleaks:v8.30.1" in texto
    assert "semgrep/semgrep:1.172.0" in texto
    assert "aquasec/trivy:0.74.0" in texto
    assert "--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1" in texto


def test_documentacao_de_governanca_permanece_versionada():
    texto = _texto(GOV_DOC)
    assert texto.strip(), "docs/GOVERNANCA_IA.md não pode ficar vazio"


def _allowlist_doc() -> list[str]:
    texto = _texto(GOV_DOC)
    assert "## 12. Exceção de bot de manutenção de dependências" in texto
    secao = texto.split("## 12. Exceção de bot de manutenção de dependências", 1)[1]
    secao = secao.split("\n## 13.", 1)[0]
    m = re.search(r"```json\s*(\[.*?\])\s*```", secao, re.S)
    assert m, "seção 12 não tem bloco JSON com a allowlist"
    return json.loads(m.group(1))


def test_allowlist_do_documento_e_a_esperada():
    assert _allowlist_doc() == ["dependabot[bot]"]


def test_fase2_referencia_o_canonico_em_vez_de_ser_fonte_propria():
    fase2 = _texto(REPO_ROOT / "docs" / "GOVERNANCA_FASE2.md")
    assert "GOVERNANCA_IA.md" in fase2 and "seção 12" in fase2
    assert "endswith" not in fase2
