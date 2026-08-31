"""Paridade entre o deploy manual e o workflow — e a recusa fora da VPS.

O deploy do EJC nunca dependeu tecnicamente do GitHub Actions: o runner está
DENTRO da VPS e a lógica mora em `deploy_workflow_transaction.sh` →
`deploy_vps_safe.sh`. O Actions é o gatilho. Só que DOIS passos críticos
existiam apenas dentro do YAML — o pré-voo e a classificação de migrations — e
quem rodasse o script de deploy na mão pularia os dois, deixando
`RUN_MIGRATIONS` no default 0: código novo contra schema antigo, em silêncio.

`scripts/deploy_manual.sh` porta esses passos. O risco que sobra é DERIVA: o
workflow ganhar uma trava nova e o caminho manual não. Estes testes travam a
paridade nos pontos que importam, e exercitam de verdade as recusas do script
(elas rodam em qualquer máquina, porque a recusa é justamente não estar na VPS).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
MANUAL = RAIZ / "scripts" / "deploy_manual.sh"
WORKFLOW = RAIZ / ".github" / "workflows" / "deploy-vps.yml"


@pytest.fixture(scope="module")
def manual() -> str:
    return MANUAL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


# Skip por TESTE, aplicado só a quem lê o YAML arquivado. A primeira versão
# desta correção pulava dentro da fixture — mas os testes de paridade afirmam,
# na MESMA função, sobre o workflow E sobre o `deploy_manual.sh`, que continua
# sendo o caminho oficial de deploy. Pular a fixture derrubava as duas metades
# e apagava justamente as travas de produção que eu dizia estar preservando:
# backup pré-deploy, bloqueio de migration não expand-only, verificação
# `/api/health` e idempotência por SHA. Onde as duas metades dividem a mesma
# função, a função se divide (achado do review do Codex no PR #1328).
sem_workflow = pytest.mark.skipif(
    not WORKFLOW.is_file(),
    reason=("GitHub Actions arquivado em 31/08 (b77ff4c) — workflows movidos "
            "para docs/arquivo/ci/github-actions-legacy/; Woodpecker é o CI oficial"),
)


# ── 1. Paridade de travas ────────────────────────────────────────────────────

# As travas de produção, em um lugar só: a metade VIVA confere que o
# `deploy_manual.sh` as tem, a metade DORMENTE que o workflow não as perdeu.
TRAVAS = [
    ("check_migration_compatibility.py",
     "sem o classificador, migration destrutiva passaria direto"),
    ("--versions-dir backend/alembic/versions",
     "classificar o diretório errado aprova qualquer coisa"),
    ("--current-revision",
     "sem a revisão atual não há como saber o que está pendente"),
    ("alembic_version",
     "a revisão tem de vir do banco de PRODUÇÃO, não de um palpite"),
    ("ejc_db",
     "deploy sem o banco no ar não pode nem começar"),
    ("deploy_workflow_transaction.sh",
     "é ele que segura o mutex host-level; chamar deploy_vps_safe.sh direto "
     "deixaria GitHub e manual se intercalarem"),
    ("RAG_EXIGIR_VIGENCIA_VERIFICADA",
     "gate de vigência ambíguo não pode tocar produção"),
    ("/api/health",
     "sem verificação pós-deploy, rollback silencioso passa por sucesso"),
]


@pytest.mark.parametrize("trava, porque", TRAVAS)
def test_manual_tem_a_trava(manual, trava, porque):
    """Metade VIVA: a trava tem que estar no script que faz o deploy hoje."""
    assert trava in manual, f"o deploy manual não tem a trava {trava!r} — {porque}"


@sem_workflow
@pytest.mark.parametrize("trava, porque", TRAVAS)
def test_workflow_tem_a_mesma_trava(workflow, trava, porque):
    """Metade de PARIDADE, dormente: só vale enquanto houver workflow."""
    assert trava in workflow, f"o workflow perdeu a trava {trava!r} — {porque}"


def test_backup_pre_deploy_e_obrigatorio_no_manual(manual):
    """A trava que protege contra o pior caso: deploy sem backup."""
    assert "REQUIRE_PREDEPLOY_BACKUP=1" in manual


@sem_workflow
def test_backup_pre_deploy_e_obrigatorio_no_workflow(workflow):
    assert 'REQUIRE_PREDEPLOY_BACKUP: "1"' in workflow


def test_migration_nao_expand_only_bloqueia_no_manual(manual):
    assert "NÃO é expand-only" in manual


@sem_workflow
def test_migration_nao_expand_only_bloqueia_no_workflow(workflow):
    assert "não é expand-only" in workflow or "Migration pendente não é expand-only" in workflow


def test_run_migrations_vem_da_classificacao_e_nao_e_fixo(manual):
    """O defeito que este script existe para evitar: `RUN_MIGRATIONS` no
    default 0 sobe código novo contra schema antigo, sem erro nenhum."""
    assert "RUN_MIGRATIONS=1" in manual and "RUN_MIGRATIONS=0" in manual
    assert 'RUN_MIGRATIONS="$RUN_MIGRATIONS"' in manual
    # A decisão precisa depender da contagem de pendentes.
    assert 'if [ "$pendentes" -gt 0 ]' in manual


def test_idempotencia_por_sha_preservada_no_manual(manual):
    assert ".deploy_last_sha" in manual


@sem_workflow
def test_idempotencia_por_sha_preservada_no_workflow(workflow):
    assert ".deploy_last_sha" in workflow


# ── 2. Recusas, exercitadas de verdade ──────────────────────────────────────

def _rodar(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(MANUAL), *args],
        cwd=RAIZ, capture_output=True, text=True, timeout=120,
    )


def test_sem_sha_mostra_uso_e_nao_faz_nada():
    r = _rodar()
    assert r.returncode == 2
    assert "uso: deploy_manual.sh" in r.stderr


def test_fora_da_vps_reprova_no_pre_voo_sem_mutar():
    """Rodar fora da VPS tem de parar no pré-voo — nunca chegar à transação.

    Este teste passa em qualquer máquina de desenvolvimento justamente porque
    ela não é a VPS: não há /opt/ejc nem container ejc_db.
    """
    r = _rodar("--sha", "0" * 40)
    assert r.returncode == 2
    assert "pré-voo reprovado" in r.stderr
    assert "nada foi tocado em produção" in r.stderr
    # A prova de que não avançou: a transação nunca foi anunciada.
    assert "mutex host-level" not in r.stdout


def test_sha_divergente_do_checkout_e_recusado():
    """Implantar um SHA diferente do que está no disco é a forma silenciosa de
    subir o que não foi revisado."""
    r = _rodar("--sha", "deadbeef")
    assert r.returncode == 2
    assert "checkout está em" in r.stderr


def test_script_e_executavel_e_tem_shebang(manual):
    assert manual.startswith("#!/usr/bin/env bash")
    assert MANUAL.stat().st_mode & 0o111, "precisa ser executável"
