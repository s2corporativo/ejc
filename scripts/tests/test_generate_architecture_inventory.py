from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "generate_architecture_inventory.py"
SPEC = importlib.util.spec_from_file_location("architecture_inventory", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ArchitectureInventoryGeneratorTest(unittest.TestCase):
    def test_detects_core_artifacts_and_applies_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "backend/app/routers").mkdir(parents=True)
            (root / "backend/app/services").mkdir(parents=True)
            (root / "backend/app/models").mkdir(parents=True)
            (root / "frontend/src/pages").mkdir(parents=True)
            (root / "frontend/src/config").mkdir(parents=True)
            (root / "config").mkdir(parents=True)

            (root / "backend/app/main.py").write_text(
                "from app.routers import cases\n"
                "app.include_router(cases.router, prefix='/api')\n",
                encoding="utf-8",
            )
            (root / "backend/app/routers/cases.py").write_text(
                "from fastapi import APIRouter\n"
                "router = APIRouter(prefix='/cases')\n"
                "@router.get('/{case_id}')\n"
                "async def obter_caso(case_id: str):\n"
                "    return {'id': case_id}\n",
                encoding="utf-8",
            )
            (root / "backend/app/services/case_service.py").write_text(
                "def normalizar_titulo(value: str) -> str:\n"
                "    return value.strip()\n",
                encoding="utf-8",
            )
            (root / "backend/app/models/case.py").write_text(
                "from app.core.database import Base\n"
                "class Case(Base):\n"
                "    __tablename__ = 'cases'\n",
                encoding="utf-8",
            )
            (root / "frontend/src/pages/Casos.tsx").write_text(
                "export default function Casos() { return null; }\n",
                encoding="utf-8",
            )
            (root / "frontend/src/config/moduleRegistry.tsx").write_text(
                "export const STAFF_ROUTES = [\n"
                "  {\n"
                "    key: 'casos',\n"
                "    path: '/casos',\n"
                "    label: 'Casos',\n"
                "    component: Casos,\n"
                "    showInNav: true,\n"
                "  },\n"
                "];\n",
                encoding="utf-8",
            )
            (root / "frontend/src/App.tsx").write_text(
                "const App = () => <Route path='/login' element={<Login />} />;\n",
                encoding="utf-8",
            )
            (root / "config/architecture_inventory_overrides.json").write_text(
                json.dumps(
                    {
                        "rules": [
                            {
                                "kind": "frontend_route",
                                "route": "/casos",
                                "classification": "manter",
                                "confidence": "alta",
                                "rationale": "Rota canônica do domínio Caso."
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = root / "inventory"
            manifest = MODULE.generate(root, output)
            payload = json.loads((output / "architecture_inventory.json").read_text(encoding="utf-8"))
            items = payload["items"]

            self.assertTrue(manifest["gate"]["all_items_classified"])
            self.assertTrue(any(item["kind"] == "page" and item["name"] == "Casos" for item in items))
            self.assertTrue(any(item["kind"] == "frontend_route" and item["route"] == "/casos" for item in items))
            self.assertTrue(any(
                item["kind"] == "endpoint"
                and item["method"] == "GET"
                and item["route"] == "/api/cases/{case_id}"
                and item["mounted"] is True
                for item in items
            ))
            self.assertTrue(any(item["kind"] == "service" and item["name"] == "case_service" for item in items))
            self.assertTrue(any(item["kind"] == "table" and item["name"] == "cases" for item in items))
            self.assertTrue(any(item["kind"] == "function" and item["name"] == "normalizar_titulo" for item in items))
            route = next(item for item in items if item["kind"] == "frontend_route" and item["route"] == "/casos")
            self.assertEqual(route["classification"], "manter")
            self.assertEqual(route["classification_source"], "override")

            for filename in (
                "README.md",
                "architecture_inventory.json",
                "architecture_inventory.csv",
                "classification_review.csv",
                "duplicate_families.json",
                "manifest.json",
            ):
                self.assertTrue((output / filename).exists(), filename)


if __name__ == "__main__":
    unittest.main()
