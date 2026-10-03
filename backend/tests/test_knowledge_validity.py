"""Testes puros: execução direta dispensa aplicação, conftest e serviços."""
import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "app/services/knowledge_validity.py"
_SPEC = importlib.util.spec_from_file_location("knowledge_validity_pure", _PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


class TemporalVerificationTests(unittest.TestCase):
    def test_valid_dates(self):
        now = datetime(2026, 9, 28, tzinfo=timezone.utc)
        for value in ["2026-09-28", "2024-02-29", "2026-09-28T00:00:00Z",
                      "2026-09-28 00:00:00", "2026-09-28T03:00:00+03:00",
                      "2026-09-27T21:00:00-03:00", " 2026-09-27 ",
                      "2026-09-27T23:59:59.123456Z"]:
            with self.subTest(value=value):
                self.assertTrue(_MODULE.verificacao_temporal_valida(value, now=now))

    def test_invalid_dates(self):
        now = datetime(2026, 9, 28, tzinfo=timezone.utc)
        for value in [None, True, 20260928, {}, [], "", "now", "infinity",
                      "data-invalida", "2026-02-29", "2026-04-31", "0000-01-01",
                      "2999-01-01", "2026-09-28T00:00:00.000001Z",
                      "2026-09-28T00:00:00-03:00", "2026-09-27T24:00:00Z",
                      "2026-09-27T23:59:60Z", "2026-09-27T12:00:00+15:00",
                      "2026-09-27\n", "20260927", "2026-09-27T12:00"]:
            with self.subTest(value=value):
                self.assertFalse(_MODULE.verificacao_temporal_valida(value, now=now))

    def test_sql_cast_is_guarded(self):
        sql = _MODULE.SQL_VERIFICACAO_TEMPORAL_VALIDA
        self.assertIn("pg_input_is_valid", sql)
        self.assertLess(sql.index("pg_input_is_valid"), sql.index("::timestamptz"))
        self.assertIn("ELSE false END), false)", sql)
        self.assertIn("CURRENT_TIMESTAMP", sql)


if __name__ == "__main__":
    unittest.main()
