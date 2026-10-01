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
    def test_mount_analysis_modern_mechanisms_and_orphans(self) -> None:
        """Mecanismos reais de montagem + órfão genuíno continua detectado."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            routers = root / "backend/app/routers"
            dpt360 = root / "backend/app/modules/dpt360"
            prompts = root / "backend/app/services/system_prompts"
            for directory in (routers, dpt360, prompts, root / "frontend/src/pages",
                              root / "frontend/src/config", root / "config"):
                directory.mkdir(parents=True, exist_ok=True)

            (root / "backend/app/main.py").write_text(
                "from app.routers import cases\n"
                "from app.routers import api_keys as api_keys_router\n"
                "from app.routers import ramos\n"
                "from app.modules.dpt360.router import router as dpt360_router\n"
                "app.include_router(                       # antes: jurisprudencia.include_router(...)\n"
                "    cases.router, prefix='/api')\n"
                "app.include_router(api_keys_router.router, prefix='/api')\n"
                "app.include_router(ramos.router, prefix='/api')\n"
                "app.include_router(dpt360_router, prefix='/api')\n",
                encoding="utf-8",
            )
            (routers / "cases.py").write_text(
                "from fastapi import APIRouter\n"
                "router = APIRouter(prefix='/cases')\n"
                "@router.get('/{case_id}')\n"
                "async def obter_caso(case_id: str):\n"
                "    return {'id': case_id}\n",
                encoding="utf-8",
            )
            (routers / "api_keys.py").write_text(
                "from fastapi import APIRouter\nrouter = APIRouter(prefix='/keys')\n",
                encoding="utf-8",
            )
            # composição por cópia de rotas (padrão real de app/routers/ramos.py)
            (routers / "ramos.py").write_text(
                "from fastapi import APIRouter\n"
                "from app.routers import ramos_civel as _ramos_civel\n"
                "router = APIRouter()\n"
                "for _r in _ramos_civel.router.routes:\n"
                "    router.add_api_route(_r.path, _r.endpoint, methods=_r.methods)\n",
                encoding="utf-8",
            )
            (routers / "ramos_civel.py").write_text(
                "from fastapi import APIRouter\n"
                "router = APIRouter(prefix='/ramos-civel')\n"
                "@router.get('/acoes')\n"
                "async def listar_acoes():\n"
                "    return []\n",
                encoding="utf-8",
            )
            # router.py montado via import do objeto com alias (bare include)
            (dpt360 / "router.py").write_text(
                "from fastapi import APIRouter\n"
                "router = APIRouter(prefix='/dpt360')\n"
                "@router.get('/resumo')\n"
                "async def resumo():\n"
                "    return {}\n",
                encoding="utf-8",
            )
            # router.py sem APIRouter: registro de configuração, não é router
            (prompts / "router.py").write_text(
                "from enum import Enum\n"
                "class TarefaIA(str, Enum):\n"
                "    RAPIDO = 'rapido'\n",
                encoding="utf-8",
            )
            # __init__.py de re-exports, sem APIRouter
            (routers / "__init__.py").write_text(
                "from app.routers import cases\n",
                encoding="utf-8",
            )
            # Pai órfão inclui filho: o filho não pode virar mounted só por
            # estar referenciado por um router que não chega ao FastAPI principal.
            (routers / "orphan_parent.py").write_text(
                "from fastapi import APIRouter\n"
                "from app.routers import orphan_child\n"
                "router = APIRouter()\n"
                "router.include_router(orphan_child.router)\n",
                encoding="utf-8",
            )
            (routers / "orphan_child.py").write_text(
                "from fastapi import APIRouter\n"
                "router = APIRouter(prefix='/orphan-child')\n"
                "@router.get('/x')\n"
                "async def x(): return {}\n",
                encoding="utf-8",
            )

            # órfão genuíno: APIRouter + endpoints, nunca incluído
            (routers / "orfaos.py").write_text(
                "from fastapi import APIRouter\n"
                "router = APIRouter(prefix='/orfaos')\n"
                "@router.get('/velho')\n"
                "async def velho():\n"
                "    return {}\n",
                encoding="utf-8",
            )
            (root / "frontend/src/pages/Inicio.tsx").write_text(
                "export default function Inicio() { return null; }\n",
                encoding="utf-8",
            )
            (root / "frontend/src/config/moduleRegistry.tsx").write_text(
                "export const STAFF_ROUTES = [\n"
                "  { key: 'inicio', path: '/inicio', label: 'Início', component: Inicio, showInNav: true },\n"
                "];\n",
                encoding="utf-8",
            )
            (root / "frontend/src/App.tsx").write_text(
                "const App = () => <Route path='/login' element={<Login />} />;\n",
                encoding="utf-8",
            )

            output = root / "inventory"
            manifest = MODULE.generate(root, output)
            payload = json.loads((output / "architecture_inventory.json").read_text(encoding="utf-8"))
            items = payload["items"]
            by_path = {item["path"]: item for item in items if item["kind"] == "router"}

            def router_item(suffix: str) -> dict:
                return next(v for k, v in by_path.items() if k.endswith(suffix))

            def item_by_path(suffix: str) -> dict:
                return next(
                    item for item in items
                    if item["path"].endswith(suffix) and item.get("line") is None
                )

            # montados pelos mecanismos modernos (bruto já deve acertar)
            self.assertTrue(router_item("routers/cases.py")["mounted"])
            self.assertTrue(router_item("routers/api_keys.py")["mounted"])
            self.assertTrue(router_item("routers/ramos.py")["mounted"])
            self.assertTrue(router_item("routers/ramos_civel.py")["mounted"])
            self.assertTrue(router_item("modules/dpt360/router.py")["mounted"])
            # endpoint do módulo composto por cópia também é montado
            self.assertTrue(any(
                item["kind"] == "endpoint" and item["route"] == "/api/ramos-civel/acoes"
                and item["mounted"] is True
                for item in items
            ))
            # não-routers: kind python_module + mounted=None.
            helper_prompt = item_by_path("system_prompts/router.py")
            helper_init = item_by_path("routers/__init__.py")
            self.assertNotEqual(helper_prompt["kind"], "router")
            self.assertEqual(helper_init["kind"], "python_module")
            self.assertIsNone(helper_prompt["mounted"])
            self.assertIsNone(helper_init["mounted"])
            self.assertNotEqual(helper_prompt["classification"], "desativar")
            # órfão genuíno segue detectado com alta confiança
            orfao = router_item("routers/orfaos.py")
            self.assertFalse(orfao["mounted"])
            self.assertEqual(orfao["classification"], "desativar")
            self.assertFalse(router_item("routers/orphan_parent.py")["mounted"])
            self.assertFalse(router_item("routers/orphan_child.py")["mounted"])
            self.assertEqual(manifest["unmounted_routers"], 3)

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
