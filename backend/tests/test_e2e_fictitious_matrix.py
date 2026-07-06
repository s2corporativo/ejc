import json
from pathlib import Path

from app.services.module_registry import module_keys_registradas


ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "qa" / "e2e" / "fictitious_matrix.json"


def _matrix():
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_matriz_e2e_cobre_todos_os_modulos_registrados():
    matrix = _matrix()
    keys_matrix = {m["module_key"] for m in matrix["modules"]}
    keys_registry = module_keys_registradas()
    assert keys_registry.issubset(keys_matrix)


def test_matriz_e2e_usa_marcador_ficticio_em_todos_os_dados_de_criacao():
    matrix = _matrix()
    marker = matrix["safety"]["marker"]
    payloads = matrix["fictional_data"]
    flattened = json.dumps(payloads, ensure_ascii=False)
    assert marker in flattened
    assert "FICTICIO" in flattened


def test_matriz_e2e_tem_protecao_contra_producao():
    matrix = _matrix()
    assert matrix["safety"]["production_guard"] is True
    assert "EJC_BASE_URL" in matrix["safety"]["required_env"]
    assert "EJC_TEST_EMAIL" in matrix["safety"]["required_env"]
    assert "EJC_TEST_PASSWORD" in matrix["safety"]["required_env"]


def test_matriz_e2e_tem_checks_api_validos():
    matrix = _matrix()
    for module in matrix["modules"]:
        assert module["module_key"]
        assert module["frontend_route"].startswith("/")
        assert module["api_checks"], module["module_key"]
        for check in module["api_checks"]:
            assert check["method"] in {"GET", "POST", "PATCH", "DELETE"}
            assert check["path"].startswith("/api/")
            assert isinstance(check["expected"], list)
            assert all(isinstance(code, int) for code in check["expected"])
