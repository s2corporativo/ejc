from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "qa/homologacao/run_homologacao.py"
SPEC = importlib.util.spec_from_file_location("ejc_homologacao", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_matrix_is_semantically_strict():
    matrix = MODULE.carregar_matriz()
    assert MODULE.validar_matriz(matrix) == []
    for scenario in matrix["cenarios"]:
        for step in scenario.get("passos", []):
            if step["tipo"] == "happy":
                assert all(200 <= code < 300 for code in step["expected"])
            if step["tipo"] == "idempotencia":
                assert 201 not in step["expected"]


def test_runtime_fixtures_are_unique_and_not_persisted_in_matrix():
    matrix = MODULE.carregar_matriz()
    first, first_marker = MODULE.preparar_fixtures(matrix)
    second, second_marker = MODULE.preparar_fixtures(matrix)
    assert first_marker != second_marker
    assert first["fixtures"]["cliente_pf"]["cpf"].isdigit()
    assert len(first["fixtures"]["cliente_pf"]["cpf"]) == 11
    assert first_marker in first["fixtures"]["cliente_pf"]["nome"]
    assert matrix["fixtures"]["cliente_pf"]["nome"] == "HOMOLOG-FICTICIO PLACEHOLDER"


def _executor_with_statuses(*statuses):
    executor = MODULE.Executor.__new__(MODULE.Executor)
    executor.caps = {"stack"}
    pending = list(statuses)
    executor.executar_passo = lambda step, matrix: MODULE.PassoResult(
        nome=step["nome"],
        tipo=step["tipo"],
        actor=step["actor"],
        method=step["method"],
        path=step["path"],
        status=pending.pop(0),
        status_code=200,
        expected=step["expected"],
    )
    return executor


def _matrix(requisitos):
    return {
        "cenarios": [
            {
                "id": "H99",
                "titulo": "Portal",
                "dimensao": "Segurança",
                "requisitos": requisitos,
                "passos": [
                    {
                        "nome": "positivo",
                        "tipo": "happy",
                        "actor": "staff",
                        "method": "GET",
                        "path": "/api/health",
                        "expected": [200],
                        "requires": ["stack"],
                    },
                    {
                        "nome": "negativo",
                        "tipo": "negativo",
                        "actor": "portal",
                        "method": "GET",
                        "path": "/api/cases",
                        "expected": [403],
                        "requires": ["stack", "portal"],
                    },
                ],
            }
        ]
    }


def test_missing_scenario_capability_blocks_result():
    executor = _executor_with_statuses(MODULE.PASS, MODULE.PASS)
    assert executor.executar(_matrix(["stack", "portal"]))[0].status == MODULE.BLOQUEADO


def test_any_blocked_declared_step_blocks_result():
    executor = _executor_with_statuses(MODULE.PASS, MODULE.BLOQUEADO)
    assert executor.executar(_matrix(["stack"]))[0].status == MODULE.BLOQUEADO
