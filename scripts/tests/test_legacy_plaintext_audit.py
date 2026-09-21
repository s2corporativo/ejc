from pathlib import Path
import importlib.util


SCRIPT = Path(__file__).parents[1] / "check_legacy_plaintext.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_legacy_plaintext", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_be11_queries_measure_only_legacy_columns():
    module = _module()
    assert set(module.QUERIES) == {"case_partes", "trabalhista_cases"}
    assert all("SELECT count" in query for query in module.QUERIES.values())
    assert all("DELETE" not in query.upper() and "DROP" not in query.upper() for query in module.QUERIES.values())


def test_be11_script_is_explicitly_non_destructive():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"destructive": False' in source
    assert "safe_for_phase_b" in source
