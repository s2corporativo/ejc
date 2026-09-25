"""Contrato arquitetural: EJC Core não pode ganhar novos imports de verticais.

A baseline representa dívida existente, não arquitetura desejada. O teste aceita a
remoção de dependências listadas, mas falha se surgir um novo importador fora do
conjunto conhecido. Isso permite desacoplamento incremental sem congelar o sistema.
"""
from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# Prefixos de módulos considerados verticais durante a refatoração #1843.
BOUNDARIES: dict[str, tuple[str, ...]] = {
    "dpt360": ("app.modules.dpt360",),
    "legacy_vertical_context": ("app.modules.legacy_verticals",),
    "environmental_model": ("app.models.environmental",),
    "especializado_model": ("app.models.especializado",),
    "ramos_router": ("app.routers.ramos",),
    "environmental_router": ("app.routers.environmental",),
    "tributario_router": ("app.routers.tributario_fiscal",),
    "ambiental_estrategia_router": ("app.routers.ambiental_estrategia",),
}

# Dívida conhecida na main de 25/09/2026. O teste é monotônico: remover um
# importador é permitido; adicionar outro exige decisão arquitetural explícita.
ALLOWED_IMPORTERS: dict[str, set[str]] = {
    "dpt360": {"main.py"},
    "legacy_vertical_context": {
        "services/case_context.py",
        "services/client_anonimizacao.py",
    },
    "environmental_model": {
        "models/__init__.py",
        "routers/compliance.py",
        "routers/trash.py",
    },
    "especializado_model": {
        "models/__init__.py",
    },
    "ramos_router": {
        "main.py",
        "routers/peca_geracao.py",
    },
    "environmental_router": {"main.py"},
    "tributario_router": {
        "main.py",
        "routers/lgpd_registros.py",
    },
    "ambiental_estrategia_router": {
        "main.py",
        "routers/lgpd_registros.py",
    },
}


def _is_vertical_file(relative: str) -> bool:
    """Arquivos internos da própria vertical não contam como Core -> vertical."""
    return (
        relative.startswith("modules/dpt360/")
        or relative.startswith("modules/legacy_verticals/")
        or relative.startswith("routers/ramos")
        or relative in {
            "routers/environmental.py",
            "routers/tributario_fiscal.py",
            "routers/ambiental_estrategia.py",
            "schemas/environmental.py",
            "schemas/areas_atuacao.py",
            "models/environmental.py",
            "models/especializado.py",
        }
    )


def _import_targets(tree: ast.AST) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                targets.add(f"{node.module}.{alias.name}")
    return targets


def _boundary_for(target: str) -> str | None:
    for boundary, prefixes in BOUNDARIES.items():
        for prefix in prefixes:
            if target == prefix or target.startswith(prefix + ".") or (
                prefix == "app.routers.ramos" and target.startswith(prefix + "_")
            ):
                return boundary
    return None


def test_core_nao_cria_novas_dependencias_em_verticais() -> None:
    actual: dict[str, set[str]] = {key: set() for key in BOUNDARIES}

    for path in APP_DIR.rglob("*.py"):
        relative = path.relative_to(APP_DIR).as_posix()
        if _is_vertical_file(relative):
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for target in _import_targets(tree):
            boundary = _boundary_for(target)
            if boundary:
                actual[boundary].add(relative)

    unexpected = {
        boundary: sorted(importers - ALLOWED_IMPORTERS[boundary])
        for boundary, importers in actual.items()
        if importers - ALLOWED_IMPORTERS[boundary]
    }

    assert not unexpected, (
        "Nova dependência EJC Core -> vertical detectada. "
        "Não amplie a baseline automaticamente: desacople o consumidor ou "
        "registre decisão arquitetural explícita na #1843. "
        f"Dependências novas: {unexpected}"
    )


def test_baseline_so_contem_arquivos_reais() -> None:
    """Evita baseline apodrecer com caminhos inventados/renomeados."""
    missing = sorted(
        importer
        for importers in ALLOWED_IMPORTERS.values()
        for importer in importers
        if not (APP_DIR / importer).is_file()
    )
    assert not missing, f"Baseline referencia arquivo inexistente: {missing}"
