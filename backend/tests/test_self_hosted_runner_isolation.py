"""Contrato: código de PR/branch não confiável nunca executa na VPS de produção.

Executor elegível para validação de PR: `ubuntu-latest` (cota gratuita do
GitHub, spending limit $0) — nunca `[self-hosted, ejc-vps]`, que hospeda
produção. Jobs manuais que tocam produção continuam exigindo main e
`environment: production` no host produtivo."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"


def _read(name: str) -> str:
    return (WF / name).read_text(encoding="utf-8")


def _job_block(texto: str, inicio: str, fim: str | None = None) -> str:
    bloco = texto.split(inicio, 1)[1]
    if fim and fim in bloco:
        bloco = bloco.split(fim, 1)[0]
    return bloco


def test_validacao_de_pr_do_backup_usa_runner_nao_produtivo():
    """O job `validar` de PR do backup-gdrive deve rodar em executor não
    produtivo (`ubuntu-latest`), isolado da VPS de produção."""
    backup = _job_block(
        _read("backup-gdrive-activation.yml"),
        "  validar:\n",
        "  comprovar-producao:\n",
    )
    assert "runs-on: ubuntu-latest" in backup
    assert "self-hosted" not in backup
    # O job de produção (comprovar-producao) permanece no host produtivo,
    # gated por workflow_dispatch em main com environment production.
    bloco_prod = _job_block(
        _read("backup-gdrive-activation.yml"),
        "  comprovar-producao:\n",
    )
    assert "runs-on: [self-hosted, ejc-vps]" in bloco_prod
    assert "environment: production" in bloco_prod


def test_workflows_de_validacao_de_pr_nao_rodam_no_host_de_producao():
    """Nenhum workflow que valida PR pode usar o runner de produção
    `[self-hosted, ejc-vps]` em job acessível por Pull Request. Workflows com
    bloco de produção manual (comprovar-producao/ativar-producao/prova)
    permanecem no host produtivo, mas esses blocos são gated por
    workflow_dispatch em main com environment production (testado em separado).
    Por isso o bloco de produção é excluído do `fim` aqui apenas quando o
    arquivo contém um job manual de produção; se o restante do arquivo
    (parte que dispara em PR) ainda contiver o runner de produção, o teste
    reprova."""
    PROD_JOBS = ("  comprovar-producao:\n", "  ativar-producao:\n", "  prova:\n")
    for nome in (
        "ci.yml",
        "ejc-release-gate.yml",
        "backup-gdrive-activation.yml",
        "architecture-refactor-wave1.yml",
        "architecture-refactor-wave2.yml",
    ):
        texto = _read(nome)
        # Remover o bloco de produção manual (gated por workflow_dispatch em
        # main + environment production — testado em separado) antes de
        # verificar que a parte de PR está limpa. O bloco só é removido quando
        # o nome do job aparece como chave de job sob "jobs:" (linha iniciando
        # com 2 espaços após "jobs:"), nunca dentro de listas de paths.
        parte_pr = texto
        idx_jobs = texto.find("jobs:\n")
        if idx_jobs != -1:
            corpo = texto[idx_jobs:]
            for prod_job in PROD_JOBS:
                prod_idx = corpo.find(prod_job)
                if prod_idx == 0 or (prod_idx != -1 and corpo[prod_idx - 1] == "\n"):
                    parte_pr = texto[: idx_jobs + prod_idx]
                    break
        assert "runs-on: [self-hosted, ejc-vps]" not in parte_pr, (
            f"{nome} expõe job de PR no runner de produção"
        )
        assert "runs-on: ubuntu-latest" in texto, (
            f"{nome} sem executor elegível ubuntu-latest"
        )


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
    restritas ao host produtivo com `environment: production` — parte segura do
    contrato que este teste protege contra enfraquecimento."""
    backup = _job_block(_read("backup-gdrive-activation.yml"), "  comprovar-producao:\n")
    rag = _job_block(_read("rag-production-activation.yml"), "  ativar-producao:\n")
    continuidade = _job_block(_read("producao-prova-continuidade.yml"), "  prova:\n")

    for bloco in (backup, rag, continuidade):
        assert "runs-on: [self-hosted, ejc-vps]" in bloco
        assert "environment: production" in bloco
