from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_facade_reuses_advanced_implementations_without_copying_them():
    source = (ROOT / "app/routers/sala_de_guerra_facade.py").read_text(
        encoding="utf-8"
    )
    assert '@router.post(\n    "/simular-contestacao"' in source
    assert '"/visual-law"' in source
    assert '@router.get("/visual-law/download")' in source
    assert "from app.routers.sala_de_guerra_v3 import simular_war_room" in source
    assert "from app.routers.sala_de_guerra_v3 import gerar_visual_law" in source
    assert "from app.routers.sala_de_guerra_v3 import download_visual_law" in source
    assert "IASentinela" not in source


def test_facade_is_attached_to_case_workspace_router():
    source = (ROOT / "app/routers/__init__.py").read_text(encoding="utf-8")
    assert "sala_de_guerra.router.include_router(sala_de_guerra_facade.router)" in source


def test_legacy_v3_router_remains_available_during_migration():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "app.include_router(sala_de_guerra_v3.router, prefix=API)" in main
    assert "app.include_router(sala_de_guerra.router, prefix=API)" in main
