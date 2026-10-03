"""Um benchmark jamais deve aceitar banco externo ou sem marca de teste."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/benchmark_preliminares_cutover.py"
spec = importlib.util.spec_from_file_location("benchmark_guard", SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.mark.parametrize("address", [
    "postgresql://db.example.invalid/ejc_test_ficticio",
    "postgresql://127.0.0.1/ejc",
    "postgresql://127.0.0.1/postgres",
    "postgresql://127.0.0.1/ejc_test_ficticio?host=db.example.invalid",
    "postgresql://127.0.0.1/ejc_test_ficticio?dbname=ejc",
    "postgresql://127.0.0.1/ejc_test_ficticio?service=externo",
])
def test_rejeita_endereco_fora_do_banco_ficticio(monkeypatch, address):
    monkeypatch.setenv("RUN_DB_TESTS", "1")
    with pytest.raises(ValueError):
        benchmark.validate_test_url(address)


def test_exige_opt_in_mesmo_para_banco_local(monkeypatch):
    monkeypatch.delenv("RUN_DB_TESTS", raising=False)
    with pytest.raises(ValueError):
        benchmark.validate_test_url("postgresql://localhost/ejc_test_ficticio")
    monkeypatch.setenv("RUN_DB_TESTS", "1")
    assert benchmark.validate_test_url("postgresql://localhost/ejc_test_ficticio").database == "ejc_test_ficticio"


@pytest.mark.parametrize("name", ["PGHOSTADDR", "PGHOST", "PGDATABASE", "PGPORT", "PGSERVICE", "PGSERVICEFILE"])
def test_libpq_nao_pode_sobrescrever_destino_pelo_ambiente(monkeypatch, name):
    monkeypatch.setenv("RUN_DB_TESTS", "1")
    monkeypatch.setenv(name, "ficticio")
    with pytest.raises(ValueError):
        benchmark.validate_test_url("postgresql+psycopg2://127.0.0.1/ejc_test_ficticio")
