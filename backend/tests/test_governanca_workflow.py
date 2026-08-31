"""Contrato de governança do CI canônico do EJC.

Desde 31/08/2026 o GitHub Actions não é mais o executor ativo. O gate oficial
é o Woodpecker self-hosted, com configuração versionada em `.woodpecker.yml`
e infraestrutura em `infra/woodpecker/`.

Estes testes protegem a arquitetura atual e evitam que regras legadas de
`governanca.yml` voltem a ser tratadas como gate executável.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WOODPECKER_PATH = REPO_ROOT / ".woodpecker.yml"
COMPOSE_PATH = REPO_ROOT / "infra" / "woodpecker" / "docker-compose.yml"
GOV_DOC = REPO_ROOT / "docs" / "GOVERNANCA_IA.md"
ACTIONS_DIR = REPO_ROOT / ".github" / "workflows"


def _texto(path: Path) -> str:
    assert path.is_file(), f"arquivo obrigatório ausente: {path.relative_to(REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_actions_ativos_permanecem_aposentados():
    if not ACTIONS_DIR.exists():
        return
    ativos = [p for p in ACTIONS_DIR.iterdir() if p.suffix in (".yml", ".yaml")]
    assert not ativos, f"não reintroduza GitHub Actions ativos: {[p.name for p in ativos]}"


def test_woodpecker_e_o_gate_canonico():
    texto = _texto(WOODPECKER_PATH)
    assert "CI oficial fora do GitHub Actions" in texto
    assert "event: push" in texto
    assert "branch: main" in texto
    assert "event: pull_request" in texto


def test_backend_tem_gates_minimos():
    texto = _texto(WOODPECKER_PATH)
    for comando in (
        "ruff check app",
        "python -m alembic heads",
        "python -m alembic upgrade head",
        "pytest tests -q",
    ):
        assert comando in texto, f"gate backend ausente: {comando}"


def test_frontend_tem_gates_minimos():
    texto = _texto(WOODPECKER_PATH)
    for comando in (
        "npm ci",
        "npm run lint",
        "npm test",
        "npm run build",
    ):
        assert comando in texto, f"gate frontend ausente: {comando}"


def test_pipeline_usa_banco_descartavel_pgvector():
    texto = _texto(WOODPECKER_PATH)
    assert "pgvector/pgvector:pg16" in texto
    assert "POSTGRES_DB: ejc_db" in texto
    assert "DATABASE_URL:" in texto
    assert "@db:5432/ejc_db" in texto


def test_servidor_e_agente_estao_fixados_na_mesma_versao():
    texto = _texto(COMPOSE_PATH)
    versao = "v3.18.0"
    assert f"woodpecker-server:{versao}" in texto
    assert f"woodpecker-agent:{versao}" in texto


def test_segredos_de_agente_e_grpc_sao_contratos_distintos():
    texto = _texto(COMPOSE_PATH)
    assert "WOODPECKER_AGENT_SECRET" in texto
    assert "WOODPECKER_GRPC_SECRET" in texto
    assert "Use segredos independentes" in texto


def test_governanca_de_pr_e_registro_de_agente_estao_restritos():
    texto = _texto(COMPOSE_PATH)
    assert "WOODPECKER_DEFAULT_APPROVAL_MODE=pull_requests" in texto
    assert "WOODPECKER_DISABLE_USER_AGENT_REGISTRATION=true" in texto


def test_documentacao_de_governanca_permanece_versionada():
    texto = _texto(GOV_DOC)
    assert texto.strip(), "docs/GOVERNANCA_IA.md não pode ficar vazio"
