"""Contrato de runners do CI (revisado em 15/08/2026 por decisão do titular).

Histórico: até 13/08/2026 o contrato exigia `ubuntu-latest` para validação de
PR ("código de PR nunca executa na VPS"). A cota gratuita GitHub-hosted do
repositório esgotou (spending limit $0) e TODO o CI ficou inoperante entre
12 e 15/08 (`startup_failure`, 0 jobs) — sem gates, regressões entraram na
main sem serem vistas. O titular decidiu operar 100% na cota gratuita, e o
único executor gratuito e ilimitado disponível é o runner self-hosted
`ejc-vps` (Issue #1147 / relatório de auditoria de 15/08).

Contrato vigente:
1. Jobs de validação de PR executam em `[self-hosted, ejc-vps]`.
2. Controles compensatórios obrigatórios (guardados por estes testes):
   a. nenhum job acessível por PR usa `environment: production` — código de
      PR não alcança os segredos do ambiente de produção;
   b. o banco dos testes do CI é um Postgres efêmero em Docker na porta
      dedicada 55432, com credenciais próprias e limpeza ao final — nunca o
      `ejc_db` de produção;
   c. jobs manuais que alcançam produção continuam restritos a main
      (`workflow_dispatch`/schedule) com `environment: production`.
3. O repositório não aceita fork externo: todo PR nasce de agente da própria
   conta. Se isso mudar (colaborador externo/fork), este contrato precisa ser
   revisto ANTES — código de terceiro não pode executar na VPS.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"

RUNNER_PROD = "runs-on: [self-hosted, ejc-vps]"

# Workflows cujos jobs de validação (PR/push) devem usar o runner gratuito.
WORKFLOWS_VALIDACAO = (
    "ci.yml",
    "ejc-release-gate.yml",
    "governanca.yml",
    "continuity-ui-gates.yml",
)


def _read(name: str) -> str:
    return (WF / name).read_text(encoding="utf-8")


def _job_block(texto: str, inicio: str, fim: str | None = None) -> str:
    bloco = texto.split(inicio, 1)[1]
    if fim and fim in bloco:
        bloco = bloco.split(fim, 1)[0]
    return bloco


def test_validacao_roda_no_runner_self_hosted_da_cota_gratuita():
    """Todos os jobs de validação usam o runner self-hosted; nenhum job de
    workflow de validação depende de executor GitHub-hosted pago/limitado."""
    for nome in WORKFLOWS_VALIDACAO:
        texto = _read(nome)
        assert RUNNER_PROD in texto, f"{nome} sem o runner da cota gratuita"
        assert "runs-on: ubuntu-latest" not in texto, (
            f"{nome} ainda depende de executor GitHub-hosted (cota esgotada "
            "deixa o workflow em startup_failure)"
        )


def test_job_de_pr_do_backup_usa_runner_gratuito_sem_environment_producao():
    backup_validar = _job_block(
        _read("backup-gdrive-activation.yml"),
        "  validar:\n",
        "  comprovar-producao:\n",
    )
    assert RUNNER_PROD in backup_validar
    assert "environment: production" not in backup_validar
    bloco_prod = _job_block(
        _read("backup-gdrive-activation.yml"),
        "  comprovar-producao:\n",
    )
    assert RUNNER_PROD in bloco_prod
    assert "environment: production" in bloco_prod


def test_jobs_de_validacao_nao_usam_environment_de_producao():
    """Controle compensatório 2a: código de PR não recebe os segredos do
    environment de produção, mesmo executando no host produtivo."""
    for nome in WORKFLOWS_VALIDACAO:
        assert "environment: production" not in _read(nome), (
            f"{nome} expõe environment de produção a job de validação"
        )


def test_ci_usa_postgres_efemero_isolado_com_limpeza():
    """Controle compensatório 2b: o CI nunca toca o ejc_db de produção —
    Postgres efêmero em container próprio, porta dedicada e remoção ao final."""
    ci = _read("ci.yml")
    assert 'CI_PG_CONTAINER: ejc-ci-pg' in ci
    assert 'CI_PG_PORT: "55432"' in ci
    assert "localhost:55432/ejc_db" in ci
    assert 'docker rm -f "$CI_PG_CONTAINER"' in ci
    assert "pgvector/pgvector:pg16" in ci


def test_jobs_manuais_que_alcancam_producao_exigem_main():
    backup = _read("backup-gdrive-activation.yml")
    rag = _read("rag-production-activation.yml")
    continuidade = _read("producao-prova-continuidade.yml")
    monitor = _read("production-backup-monitor.yml")
    staging = _read("deploy-staging.yml")
    deploy = _read("deploy-vps.yml")

    assert "github.event_name == 'workflow_dispatch' && github.ref_name == 'main'" in backup
    assert "github.event_name == 'workflow_dispatch' && github.ref_name == 'main'" in rag
    assert "if: github.ref_name == 'main'" in continuidade
    assert "github.event_name == 'schedule' || github.ref_name == 'main'" in monitor
    assert "github.ref == 'refs/heads/main'" in staging
    assert "github.ref_name == 'main'" in deploy


def test_workflows_de_producao_fazem_checkout_da_main_ou_sha_aprovado():
    backup = _read("backup-gdrive-activation.yml")
    continuidade = _read("producao-prova-continuidade.yml")
    monitor = _read("production-backup-monitor.yml")
    rag = _read("rag-production-activation.yml")
    deploy = _read("deploy-vps.yml")

    assert "ref: main" in backup
    assert "ref: main" in continuidade
    assert "ref: main" in monitor
    assert "ref: ${{ github.sha }}" in rag
    assert "ref: ${{ env.TARGET_SHA }}" in deploy


def test_operacoes_manuais_sensiveis_usam_environment_de_producao():
    """Operações que alcançam produção (backup, RAG, continuidade) permanecem
    restritas ao host produtivo com `environment: production` — parte do
    contrato preservada sem alteração."""
    backup = _job_block(_read("backup-gdrive-activation.yml"), "  comprovar-producao:\n")
    rag = _job_block(_read("rag-production-activation.yml"), "  ativar-producao:\n")
    continuidade = _job_block(_read("producao-prova-continuidade.yml"), "  prova:\n")

    for bloco in (backup, rag, continuidade):
        assert RUNNER_PROD in bloco
        assert "environment: production" in bloco
