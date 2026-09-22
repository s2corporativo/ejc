from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER_PATH = ROOT / "scripts" / "tests" / "classify_pytest_results.py"


def _classifier_module():
    spec = importlib.util.spec_from_file_location(
        "ejc_classify_pytest_results", CLASSIFIER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CIEvidenceContract(unittest.TestCase):
    def test_db_skip_obrigatorio_e_bloqueante(self):
        module = _classifier_module()
        xml = """<testsuite>
          <testcase classname="tests.test_schema_sync" name="test_metadata_bate_com_banco_real">
            <skipped message="SCHEMA_CHECK_DATABASE_URL não definida — checagem pulada"/>
          </testcase>
          <testcase classname="tests.test_rag" name="test_rag_rowlevel">
            <skipped message="requer Postgres+pgvector com migrations"/>
          </testcase>
          <testcase classname="tests.test_schema" name="test_colunas">
            <skipped message="Banco inacessível para checagem de coluna"/>
          </testcase>
        </testsuite>"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "junit.xml"
            path.write_text(xml, encoding="utf-8")
            report = module.classify(path)
        self.assertEqual(report["counts"]["skip"], 3)
        self.assertEqual(report["blocking_db_skip_count"], 3)

    def test_classificacao_separa_infra_endpoint_e_teste(self):
        module = _classifier_module()
        xml = """<testsuite>
          <testcase classname="tests.test_conn" name="test_pg">
            <error message="socket.gaierror">temporary failure in name resolution</error>
          </testcase>
          <testcase classname="tests.test_api" name="test_health">
            <failure message="status_code 500">HTTP 500</failure>
          </testcase>
          <testcase classname="tests.test_logic" name="test_regra">
            <failure message="assertion failed">AssertionError</failure>
          </testcase>
        </testsuite>"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "junit.xml"
            path.write_text(xml, encoding="utf-8")
            report = module.classify(path)
        self.assertEqual(report["counts"]["infra_error"], 1)
        self.assertEqual(report["counts"]["endpoint_failure"], 1)
        self.assertEqual(report["counts"]["test_failure"], 1)

    def test_smoke_nao_aceita_404_em_rota_critica(self):
        script = (ROOT / "scripts" / "tests" / "test_live_api.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("401|403|404|405|422", script)
        for route in ("/api/cases", "/api/documents", "/api/rag/buscar"):
            self.assertIn(route, script)

    def test_woodpecker_exige_db_real_e_classificador_fail_closed(self):
        workflow = (ROOT / ".woodpecker.yml").read_text(encoding="utf-8")
        self.assertIn("pgvector/pgvector:pg16@sha256:", workflow)
        self.assertIn("alembic upgrade head", workflow)
        self.assertIn("[db-evidence]", workflow)
        self.assertIn("--fail-on-db-skip", workflow)
        self.assertIn("test_ci_evidence_contract.py", workflow)


if __name__ == "__main__":
    unittest.main()
