"""Guardas da configuração de CI após a migração para Woodpecker.

O GitHub Actions foi aposentado em 31/08/2026 e os workflows ativos foram
arquivados. O CI canônico do EJC passou a ser `.woodpecker.yml`.

Este teste impede duas regressões:
1. reintroduzir workflows ativos em `.github/workflows`;
2. remover ou tornar inválido o pipeline Woodpecker canônico.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIONS_DIR = REPO_ROOT / ".github" / "workflows"
WOODPECKER_PATH = REPO_ROOT / ".woodpecker.yml"
ARCHIVE_DIR = REPO_ROOT / "docs" / "arquivo" / "ci" / "github-actions-legacy" / "2026-08-31"


def _actions_ativos() -> list[Path]:
    if not ACTIONS_DIR.exists():
        return []
    return sorted(
        p for p in ACTIONS_DIR.iterdir() if p.is_file() and p.suffix in (".yml", ".yaml")
    )


def test_github_actions_nao_esta_ativo():
    ativos = _actions_ativos()
    assert not ativos, (
        "GitHub Actions foi aposentado; não reintroduza workflows ativos. "
        f"Encontrados: {[p.name for p in ativos]}"
    )


def test_historico_dos_actions_foi_preservado():
    assert ARCHIVE_DIR.is_dir(), "arquivo histórico dos GitHub Actions desapareceu"
    assert any(ARCHIVE_DIR.rglob("*.yml")), "arquivo histórico não contém workflows preservados"


def test_woodpecker_pipeline_existe():
    assert WOODPECKER_PATH.is_file(), ".woodpecker.yml é o CI canônico e precisa existir"


def test_woodpecker_declara_gatilhos_e_gates_essenciais():
    texto = WOODPECKER_PATH.read_text(encoding="utf-8")
    for trecho in (
        "event: push",
        "branch: main",
        "event: pull_request",
        "backend:",
        "frontend:",
        "ruff check app",
        "python -m alembic upgrade head",
        "pytest tests -q",
        "npm ci",
        "npm run lint",
        "npm test",
        "npm run build",
    ):
        assert trecho in texto, f"gate obrigatório ausente de .woodpecker.yml: {trecho}"


def test_woodpecker_yaml_carrega():
    yaml = pytest.importorskip("yaml", reason="PyYAML ausente; guardas textuais seguem ativos")
    dados = yaml.safe_load(WOODPECKER_PATH.read_text(encoding="utf-8"))
    assert isinstance(dados, dict), ".woodpecker.yml não carregou como mapa YAML"
    assert "steps" in dados and isinstance(dados["steps"], dict)
    assert {"backend", "frontend"}.issubset(dados["steps"])
    assert "services" in dados and "db" in dados["services"]
