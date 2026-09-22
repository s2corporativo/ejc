from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


BENCHMARK = Path(__file__).resolve().parents[1] / "app" / "eval" / "benchmarks" / "rag_source_curated.jsonl"


def _rows() -> list[dict]:
    return [json.loads(line) for line in BENCHMARK.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_benchmark_tem_itens_de_fontes_verificadas_nao_geradas_por_ia():
    rows = _rows()
    assert len(rows) == 14
    assert all(row["status"] == "fonte_curada" for row in rows)
    assert all(row["ficticio"] is True for row in rows)
    assert all(row["atestado_por"] is None for row in rows)
    assert all(row["proveniencia"]["gerado_por_IA"] == "false" for row in rows)
    assert all(row["proveniencia"]["last_verified_at"] for row in rows)


def test_benchmark_preserva_fontes_https_oficiais_e_snapshot():
    rows = _rows()
    for row in rows:
        assert row["expected_sources"]
        assert all(urlparse(url).scheme == "https" for url in row["expected_sources"])
        assert len(row["proveniencia"]["sha256_snapshot_local"]) == 64
        assert row["proveniencia"]["arquivo"].startswith("docs/biblioteca_juridica/")
