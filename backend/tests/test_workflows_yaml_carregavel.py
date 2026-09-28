"""Guardas da configuração canônica de CI: GitHub Actions + Coolify.

O CI de Pull Request executa somente em runners GitHub-hosted. O Woodpecker pode
permanecer versionado durante a janela de transição, mas não é a arquitetura-alvo
nem pode ser requisito para os novos gates.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIONS_DIR = REPO_ROOT / ".github" / "workflows"
CI_PATH = ACTIONS_DIR / "ci.yml"
WOODPECKER_PATH = REPO_ROOT / ".woodpecker.yml"
ARCHIVE_DIR = REPO_ROOT / "docs" / "arquivo" / "ci" / "github-actions-legacy" / "2026-08-31"


def _actions_ativos() -> list[Path]:
    if not ACTIONS_DIR.exists():
        return []
    return sorted(
        p for p in ACTIONS_DIR.iterdir() if p.is_file() and p.suffix in (".yml", ".yaml")
    )


def test_github_actions_esta_ativo():
    ativos = _actions_ativos()
    assert CI_PATH in ativos, "workflow canônico .github/workflows/ci.yml ausente"


def test_historico_dos_actions_foi_preservado():
    assert ARCHIVE_DIR.is_dir(), "arquivo histórico dos GitHub Actions desapareceu"
    assert any(ARCHIVE_DIR.rglob("*.yml")), "arquivo histórico não contém workflows preservados"


def test_ci_usa_apenas_runner_github_hosted():
    texto = CI_PATH.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-latest" in texto
    assert "runs-on: [self-hosted" not in texto
    assert "ejc-vps" not in texto


def test_ci_declara_gates_equivalentes_ao_woodpecker():
    texto = CI_PATH.read_text(encoding="utf-8")
    for trecho in (
        "Secret scanning bloqueante",
        "Contratos operacionais leves",
        "Contratos de deploy e rollback",
        "DAG Alembic e compatibilidade expand-only",
        "Backend — lint + schema + suíte completa",
        "Frontend — lint + testes + build",
        "Agentes — contratos operacionais",
        "Segurança — Semgrep SAST",
        "Segurança — Trivy vulnerabilidades",
        "EJC Gate — Actions",
        "gitleaks/gitleaks:v8.30.1",
        "semgrep/semgrep:1.172.0",
        "aquasec/trivy:0.74.0",
        "python -m alembic upgrade head",
        "pytest tests -q",
        "npm ci --prefer-offline",
        "npm run lint",
        "npm test",
        "npm run build",
    ):
        assert trecho in texto, f"gate obrigatório ausente de ci.yml: {trecho}"


def test_ci_otimiza_execucao_sem_reduzir_gate():
    texto = CI_PATH.read_text(encoding="utf-8")
    assert "cancel-in-progress:" in texto
    assert "Escopo — detectar gates necessários" in texto
    assert "success|skipped" in texto
    assert "fail-closed" in texto


def test_ci_yaml_carrega():
    yaml = pytest.importorskip("yaml", reason="PyYAML ausente; guardas textuais seguem ativos")
    dados = yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))
    assert isinstance(dados, dict), "ci.yml não carregou como mapa YAML"
    jobs = dados.get("jobs")
    assert isinstance(jobs, dict)
    assert {
        "changes",
        "guard",
        "backend",
        "eval",
        "frontend",
        "agents",
        "security-sast",
        "security-vulnerabilities",
        "gate",
    }.issubset(jobs)


def test_fallback_woodpecker_nao_e_requisito_do_ci_canonico():
    doc = (REPO_ROOT / "docs" / "CI_CD_GITHUB_COOLIFY.md").read_text(encoding="utf-8")
    assert "GitHub Actions" in doc and "Coolify" in doc
    if WOODPECKER_PATH.exists():
        assert "fallback temporário" in doc
