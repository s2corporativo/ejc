from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_documentation_consistency import check_repository


WORKFLOWS = {
    "ci.yml": "CI",
    "release.yml": "EJC Release Gate",
    "continuity.yml": "Continuity and UI Gates",
    "inventory.yml": "Architecture Inventory — Phase 0",
}


class DocumentationConsistencyTest(unittest.TestCase):
    def _repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "docs").mkdir(parents=True)
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "docs" / "gate.md").write_text("# Gate\n", encoding="utf-8")
        (root / "README.md").write_text(
            "# EJC\n\nFontes canônicas:\n\n- `docs/gate.md` — gate oficial.\n",
            encoding="utf-8",
        )
        for filename, name in WORKFLOWS.items():
            (root / ".github" / "workflows" / filename).write_text(
                f"name: {name}\n", encoding="utf-8"
            )
        return temp, root

    def test_repositorio_consistente(self):
        temp, root = self._repo()
        self.addCleanup(temp.cleanup)
        self.assertEqual(check_repository(root), [])

    def test_fonte_canonica_ausente(self):
        temp, root = self._repo()
        self.addCleanup(temp.cleanup)
        (root / "docs" / "gate.md").unlink()
        self.assertIn(
            "Fonte canônica ausente: docs/gate.md",
            check_repository(root),
        )

    def test_link_relativo_quebrado(self):
        temp, root = self._repo()
        self.addCleanup(temp.cleanup)
        (root / "docs" / "gate.md").write_text(
            "[Runbook](missing.md)\n", encoding="utf-8"
        )
        errors = check_repository(root)
        self.assertTrue(any("Link relativo quebrado" in error for error in errors))

    def test_contagem_manual_no_readme(self):
        temp, root = self._repo()
        self.addCleanup(temp.cleanup)
        with (root / "README.md").open("a", encoding="utf-8") as stream:
            stream.write("O sistema possui 123 routers.\n")
        errors = check_repository(root)
        self.assertTrue(any("contagem arquitetural manual" in error for error in errors))

    def test_workflow_obrigatorio_ausente(self):
        temp, root = self._repo()
        self.addCleanup(temp.cleanup)
        (root / ".github" / "workflows" / "ci.yml").unlink()
        errors = check_repository(root)
        self.assertIn("Workflow obrigatório não localizado pelo nome: CI", errors)


if __name__ == "__main__":
    unittest.main()
