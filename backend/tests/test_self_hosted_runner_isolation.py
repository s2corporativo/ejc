"""Contrato: código de PR/branch não confiável nunca executa na VPS de produção."""

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


def test_validacoes_de_pr_backup_e_rag_usam_runner_hospedado():
    backup = _job_block(
        _read("backup-gdrive-activation.yml"),
        "  validar:\n",
        "  comprovar-producao:\n",
    )
    rag = _job_block(
        _read("rag-production-activation.yml"),
        "  validar:\n",
        "  ativar-producao:\n",
    )
    for bloco in (backup, rag):
        assert "runs-on: ubuntu-latest" in bloco
        assert "ejc-vps" not in bloco


def test_codmods_de_branch_nao_rodam_no_host_de_producao():
    for nome in (
        "architecture-refactor-wave1.yml",
        "architecture-refactor-wave2.yml",
    ):
        texto = _read(nome)
        assert "runs-on: ubuntu-latest" in texto
        assert "ejc-vps" not in texto


def test_gates_bloqueantes_usam_runner_ci_isolado_e_nunca_ejc_vps():
    workflows = (
        "ci.yml",
        "governanca.yml",
        "ejc-release-gate.yml",
        "architecture-inventory.yml",
        "continuity-ui-gates.yml",
    )
    for nome in workflows:
        texto = _read(nome)
        assert "ejc-ci" in texto, nome
        assert "ejc-ci-isolado" in texto, nome
        assert "runs-on: ubuntu-latest" not in texto, nome
        assert "runs-on: [self-hosted, ejc-vps]" not in texto, nome


def test_fallback_recusa_runner_produtivo_e_forks():
    texto = _read("ci-fallback-selfhosted.yml")
    assert "ejc-ci-isolado" in texto
    assert "ejc-vps" not in texto
    assert "head_repository.full_name" in texto
    assert "persist-credentials: false" in texto


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
    backup = _job_block(_read("backup-gdrive-activation.yml"), "  comprovar-producao:\n")
    rag = _job_block(_read("rag-production-activation.yml"), "  ativar-producao:\n")
    continuidade = _job_block(_read("producao-prova-continuidade.yml"), "  prova:\n")

    for bloco in (backup, rag, continuidade):
        assert "runs-on: [self-hosted, ejc-vps]" in bloco
        assert "environment: production" in bloco
