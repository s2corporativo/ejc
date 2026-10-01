import tempfile
import unittest
from pathlib import Path

from scripts.ci_affected_tests import select_backend, select_frontend


class AffectedTestsTest(unittest.TestCase):
    def _touch(self, root: Path, rel: str, content: str = "") -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_backend_seleciona_teste_direto_e_contratos(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self._touch(root, "backend/tests/test_alembic_single_head.py")
            self._touch(root, "backend/tests/test_rotas_registro_explicito.py")
            self._touch(root, "backend/tests/test_fees.py", "from app.routers import fees")
            self._touch(root, "backend/app/routers/fees.py")
            result = select_backend(root, ["backend/app/routers/fees.py"])
        self.assertIn("tests/test_fees.py", result)
        self.assertIn("tests/test_alembic_single_head.py", result)
        self.assertIn("tests/test_rotas_registro_explicito.py", result)

    def test_backend_migration_adiciona_contratos_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for rel in (
                "backend/tests/test_alembic_single_head.py",
                "backend/tests/test_rotas_registro_explicito.py",
                "backend/tests/test_migration_reservations_head.py",
                "backend/tests/test_migrations_reais_passam_no_gate.py",
                "backend/tests/test_schema_dr_parity.py",
            ):
                self._touch(root, rel)
            result = select_backend(root, ["backend/alembic/versions/999_x.py"])
        self.assertIn("tests/test_schema_dr_parity.py", result)
        self.assertIn("tests/test_migrations_reais_passam_no_gate.py", result)

    def test_frontend_seleciona_teste_do_componente(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self._touch(root, "frontend/src/config/canonicalNavigation.test.ts")
            self._touch(root, "frontend/src/pages/DashboardUltra.tsx")
            self._touch(root, "frontend/src/pages/DashboardUltra.test.tsx")
            result = select_frontend(root, ["frontend/src/pages/DashboardUltra.tsx"])
        self.assertIn("src/pages/DashboardUltra.test.tsx", result)
        self.assertIn("src/config/canonicalNavigation.test.ts", result)


if __name__ == "__main__":
    unittest.main()
