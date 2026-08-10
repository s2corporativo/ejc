"""Contrato do CI local/fallback autônomo.

Este teste é deliberadamente estático: garante que o mecanismo de fallback
continue cobrindo os gates críticos e não volte a depender de hacks temporários
no package.json para diagnosticar falhas remotas.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CI_LOCAL = ROOT / "scripts" / "ci-local.sh"
DOC = ROOT / "docs" / "CI_SEM_GITHUB.md"
AGENTS = ROOT / "AGENTS.md"


def test_ci_local_tem_sintaxe_shell_valida():
    proc = subprocess.run(
        ["bash", "-n", str(CI_LOCAL)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_ci_local_cobre_gates_criticos_sem_postinstall_diagnostico():
    source = CI_LOCAL.read_text(encoding="utf-8")

    obrigatorios = (
        "npm run format:check",
        "npm run test -- --reporter=dot",
        "npm audit --audit-level=high",
        "npm run lint:eslint",
        "npm run build",
        "ruff check app",
        "pip-audit",
        "alembic upgrade head",
        "--cov-fail-under=65",
        "app.eval.run_eval --smoke",
        "app.eval.agent_trajectory",
        "scripts/ci_guard.sh",
        "test_backup_wrapper.sh",
        "test_deploy_rollback.sh",
        "test_selfhosted_runner_setup.sh",
        "restore_drill.py",
        "test:responsive",
        "test:premium-responsive",
        "generate_architecture_inventory.py",
        "refine_architecture_inventory.py",
        "parity)",
    )
    ausentes = [token for token in obrigatorios if token not in source]
    assert not ausentes, f"gates ausentes do ci-local: {ausentes}"

    # Diagnóstico não pode ser obtido adulterando lifecycle do npm.
    assert '"postinstall"' not in source
    assert "npm pkg set" not in source


def test_politica_de_fallback_e_automatica_e_fail_closed():
    doc = DOC.read_text(encoding="utf-8").lower()
    agents = AGENTS.read_text(encoding="utf-8").lower()

    assert "não é necessário pedir autorização ao titular" in doc
    assert "não marque `full`/`parity` como verde" in doc
    assert "nunca" in agents and "postinstall" in agents
    assert "scripts/ci-local.sh" in agents
    assert "indisponibilidade remota nunca autoriza escrita direta na `main`" in agents
