from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_SCRIPTS = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GENERATOR = load("inventory_generator_test", ROOT_SCRIPTS / "generate_architecture_inventory.py")
REFINER = load("inventory_refiner_test", ROOT_SCRIPTS / "refine_architecture_inventory.py")


class RefineArchitectureInventoryTest(unittest.TestCase):
    def test_resolves_alias_and_indirect_mount_without_cross_layer_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            routers = root / "backend/app/routers"
            models = root / "backend/app/models"
            services = root / "backend/app/services"
            pages = root / "frontend/src/pages"
            config = root / "config"
            scripts = root / "scripts"
            for directory in (routers, models, services, pages, config, scripts):
                directory.mkdir(parents=True, exist_ok=True)

            # O refinador carrega o gerador a partir da raiz que está sendo
            # inventariada. A fixture deve reproduzir esse contrato, em vez de
            # depender acidentalmente do checkout real do teste.
            (scripts / "generate_architecture_inventory.py").write_text(
                (ROOT_SCRIPTS / "generate_architecture_inventory.py").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            (root / "backend/app/main.py").write_text(
                "from app.routers import parent\n"
                "from app.routers import api_keys as api_keys_router\n"
                "app.include_router(parent.router, prefix='/api')\n"
                "app.include_router(api_keys_router.router, prefix='/api')\n",
                encoding="utf-8",
            )
            (routers / "parent.py").write_text(
                "from fastapi import APIRouter\nrouter = APIRouter(prefix='/parent')\n",
                encoding="utf-8",
            )
            (routers / "child.py").write_text(
                "from fastapi import APIRouter\n"
                "router = APIRouter(prefix='/child')\n"
                "@router.get('/status')\n"
                "async def status(): return {'ok': True}\n",
                encoding="utf-8",
            )
            (routers / "api_keys.py").write_text(
                "from fastapi import APIRouter\nrouter = APIRouter(prefix='/api-keys')\n",
                encoding="utf-8",
            )
            (routers / "__init__.py").write_text(
                "from app.routers import parent, child\n"
                "parent.router.include_router(child.router)\n",
                encoding="utf-8",
            )
            (routers / "case.py").write_text(
                "from fastapi import APIRouter\nrouter = APIRouter(prefix='/case')\n",
                encoding="utf-8",
            )
            (models / "case.py").write_text(
                "from app.core.database import Base\n"
                "class Case(Base):\n    __tablename__ = 'cases'\n",
                encoding="utf-8",
            )
            (routers / "data_room.py").write_text(
                "from fastapi import APIRouter\nrouter = APIRouter(prefix='/room')\n",
                encoding="utf-8",
            )
            (routers / "data_room_v4.py").write_text(
                "from fastapi import APIRouter\nrouter = APIRouter(prefix='/room-v4')\n",
                encoding="utf-8",
            )
            (config / "architecture_inventory_overrides.json").write_text(
                json.dumps({"rules": []}), encoding="utf-8"
            )

            output = root / "inventory"
            GENERATOR.generate(root, output)
            manifest = REFINER.refine(root, output)
            payload = json.loads(
                (output / "architecture_inventory.json").read_text(encoding="utf-8")
            )
            items = payload["items"]

            child = next(
                item
                for item in items
                if item["kind"] == "router" and item["path"].endswith("child.py")
            )
            alias = next(
                item
                for item in items
                if item["kind"] == "router"
                and item["path"].endswith("api_keys.py")
            )
            init_module = next(
                item
                for item in items
                if item["path"].endswith("routers/__init__.py")
                and item["line"] is None
            )
            self.assertTrue(child["mounted"])
            self.assertTrue(alias["mounted"])
            self.assertEqual(init_module["kind"], "python_module")
            self.assertEqual(
                manifest["unmounted_routers"], 3
            )  # case + duas versões data_room não montadas

            duplicates = json.loads(
                (output / "duplicate_families.json").read_text(encoding="utf-8")
            )
            all_paths = [path for paths in duplicates.values() for path in paths]
            self.assertIn("backend/app/routers/data_room.py", all_paths)
            self.assertIn("backend/app/routers/data_room_v4.py", all_paths)
            case_groups = [
                paths
                for paths in duplicates.values()
                if any(path.endswith("/case.py") for path in paths)
            ]
            self.assertFalse(
                case_groups, "model e router do mesmo domínio não são duplicidade"
            )


if __name__ == "__main__":
    unittest.main()
