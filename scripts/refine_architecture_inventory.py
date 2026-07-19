#!/usr/bin/env python3
"""Refina o inventário bruto com análise de montagem indireta e duplicidade real.

O gerador base privilegia cobertura. Este segundo passe corrige duas fontes comuns
de falso positivo:

1. routers anexados a outros routers por ``include_router`` antes de chegarem ao
   ``main.py``;
2. arquivos de camadas diferentes com o mesmo domínio (model/router/service),
   que são arquitetura normal e não duplicidade.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def load_generator(root: Path):
    # Carrega o gerador ao lado DESTE arquivo (mesmo pacote scripts/), não do
    # `root` analisado: `root` é o repositório sob inspeção — no uso real é o
    # próprio EJC (onde os dois coincidem por acaso), mas em testes que
    # analisam uma árvore sintética num tmpdir não há cópia dos scripts ali,
    # o que quebrava com FileNotFoundError.
    script = Path(__file__).resolve().with_name("generate_architecture_inventory.py")
    spec = importlib.util.spec_from_file_location("architecture_inventory_generator", script)
    if not spec or not spec.loader:
        raise RuntimeError(f"Não foi possível carregar {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def module_path(root: Path, module: str) -> str | None:
    if not module.startswith("app."):
        return None
    candidate = root / "backend" / Path(*module.split("."))
    file_candidate = candidate.with_suffix(".py")
    init_candidate = candidate / "__init__.py"
    if file_candidate.exists():
        return file_candidate.relative_to(root).as_posix()
    if init_candidate.exists():
        return init_candidate.relative_to(root).as_posix()
    return None


def resolve_symbol(expr: ast.AST, symbols: dict[str, str], current_path: str) -> str | None:
    if isinstance(expr, ast.Name):
        if expr.id in symbols:
            return symbols[expr.id]
        if expr.id in {"router", "api_router"}:
            return current_path
        return None
    if isinstance(expr, ast.Attribute):
        base = resolve_symbol(expr.value, symbols, current_path)
        if base:
            return base
        root_name = dotted_name(expr).split(".", 1)[0]
        return symbols.get(root_name)
    return None


def import_symbols(root: Path, tree: ast.AST) -> dict[str, str]:
    symbols: dict[str, str] = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "app.routers" or node.module == "app.integrations":
                for alias in node.names:
                    module = f"{node.module}.{alias.name}"
                    resolved = module_path(root, module)
                    if resolved:
                        symbols[alias.asname or alias.name] = resolved
            elif node.module.startswith("app."):
                resolved = module_path(root, node.module)
                if resolved:
                    for alias in node.names:
                        symbols[alias.asname or alias.name] = resolved
        elif isinstance(node, ast.Import):
            for alias in node.names:
                resolved = module_path(root, alias.name)
                if resolved:
                    symbols[alias.asname or alias.name.split(".")[-1]] = resolved
    return symbols


def local_router_variables(tree: ast.AST) -> set[str]:
    variables: set[str] = set()
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or dotted_name(value.func).split(".")[-1] != "APIRouter":
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                variables.add(target.id)
    return variables


def mounted_router_paths(root: Path) -> tuple[set[str], dict[str, list[str]], set[str]]:
    """Retorna paths montados, grafo de mounts e arquivos que declaram APIRouter."""
    app_root = root / "backend/app"
    root_key = "<fastapi-app>"
    graph: dict[str, set[str]] = defaultdict(set)
    router_declarations: set[str] = set()

    for path in sorted(app_root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=relative)
        except SyntaxError:
            continue
        symbols = import_symbols(root, tree)
        local_routers = local_router_variables(tree)
        if local_routers:
            router_declarations.add(relative)
            for variable in local_routers:
                symbols[variable] = relative

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "include_router" or not node.args:
                continue
            parent_expr = node.func.value
            if isinstance(parent_expr, ast.Name) and parent_expr.id == "app":
                parent = root_key
            else:
                parent = resolve_symbol(parent_expr, symbols, relative)
            child = resolve_symbol(node.args[0], symbols, relative)
            if parent and child:
                graph[parent].add(child)

    mounted: set[str] = set()
    queue: deque[str] = deque(graph.get(root_key, set()))
    while queue:
        current = queue.popleft()
        if current in mounted:
            continue
        mounted.add(current)
        queue.extend(graph.get(current, set()))

    return mounted, {key: sorted(value) for key, value in graph.items()}, router_declarations


def normalized_stem(path: str) -> str:
    stem = Path(path).stem.lower()
    stem = re.sub(r"_(?:router|service)$", "", stem)
    stem = re.sub(r"_(?:v|version)?\d+$", "", stem)
    stem = re.sub(r"(?:modern|luxury|legacy|old)$", "", stem)
    return stem.strip("_-")


def refined_duplicate_families(items: Iterable[Any]) -> dict[str, list[str]]:
    """Agrupa apenas arquivos da mesma camada e do mesmo diretório."""
    eligible = {"router", "service", "page", "component", "model_file"}
    grouped: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for item in items:
        if item.kind not in eligible:
            continue
        parent = Path(item.path).parent.as_posix()
        family = normalized_stem(item.path)
        grouped[(item.kind, parent, family)].add(item.path)

    result: dict[str, list[str]] = {}
    for (kind, parent, family), paths in grouped.items():
        if len(paths) < 2:
            continue
        result[f"{kind}:{parent}:{family}"] = sorted(paths)
    return dict(sorted(result.items()))


def refine(root: Path, output: Path) -> dict[str, Any]:
    generator = load_generator(root)
    inventory_path = output / "architecture_inventory.json"
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    items = [generator.InventoryItem(**raw) for raw in payload["items"]]

    mounted, mount_graph, router_declarations = mounted_router_paths(root)

    # Corrige o tipo de arquivos em pastas routers que não declaram APIRouter.
    for item in items:
        if item.kind == "router" and item.path not in router_declarations:
            item.kind = "python_module"
            item.mounted = None
            item.active = True
            if item.classification_source == "mount-analysis":
                item.classification = "manter"
                item.classification_source = "refined-default"
                item.confidence = "média"
                item.rationale = "Módulo auxiliar de registro; não declara APIRouter próprio."
                item.needs_review = True

    # Corrige montagem direta, por alias e por composição recursiva de routers.
    for item in items:
        if item.kind not in {"router", "endpoint"}:
            continue
        is_mounted = item.path in mounted
        item.mounted = is_mounted
        item.active = is_mounted
        if is_mounted and item.classification_source == "mount-analysis":
            item.classification = "manter"
            item.classification_source = "refined-mount-analysis"
            item.confidence = "alta"
            item.rationale = "Router alcançável por composição recursiva de include_router até o FastAPI principal."
            item.needs_review = False
        elif not is_mounted and item.classification_source in {
            "conservative-default", "refined-mount-analysis"
        }:
            item.classification = "desativar"
            item.classification_source = "mount-analysis"
            item.confidence = "alta"
            item.rationale = "Router/endpoint sem caminho de include_router até o FastAPI principal."
            item.needs_review = True

    # Remove a falsa duplicidade entre camadas normais do mesmo domínio.
    for item in items:
        if item.classification_source == "duplicate-family":
            item.classification = "manter"
            item.classification_source = "refined-default"
            item.confidence = "baixa"
            item.rationale = "Mesma nomenclatura em camada distinta não caracteriza duplicidade funcional."
            item.needs_review = True

    duplicate_map = refined_duplicate_families(items)
    duplicate_paths = {path for paths in duplicate_map.values() for path in paths}
    for item in items:
        if item.path not in duplicate_paths:
            continue
        if item.kind not in {"router", "service", "page", "component", "model_file"}:
            continue
        if item.classification_source in {"override", "parent-override"}:
            continue
        item.classification = "consolidar"
        item.classification_source = "refined-duplicate-family"
        item.confidence = "média"
        item.rationale = "Implementações paralelas da mesma camada e diretório exigem validação de contrato e consolidação."
        item.needs_review = True

    items.sort(key=lambda item: (item.kind, item.path, item.line or 0, item.name, item.route or ""))
    generator.duplicate_families = refined_duplicate_families

    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["refined"] = True
    payload["mount_graph"] = mount_graph
    payload["items"] = [asdict(item) for item in items]
    inventory_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    generator.write_csv(output / "architecture_inventory.csv", items)
    generator.write_csv(output / "classification_review.csv", [item for item in items if item.needs_review])
    (output / "duplicate_families.json").write_text(
        json.dumps(duplicate_map, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    generator.write_markdown(output / "README.md", items, payload["source_fingerprint"])

    invalid = [item.id for item in items if item.classification not in generator.CLASSIFICATIONS]
    manifest = {
        "total": len(items),
        "by_kind": dict(sorted(Counter(item.kind for item in items).items())),
        "by_classification": dict(sorted(Counter(item.classification for item in items).items())),
        "needs_review": sum(item.needs_review for item in items),
        "unmounted_routers": sum(item.kind == "router" and item.mounted is False for item in items),
        "mounted_routers": sum(item.kind == "router" and item.mounted is True for item in items),
        "indirect_mount_edges": sum(len(children) for children in mount_graph.values()),
        "source_fingerprint": payload["source_fingerprint"],
        "refined": True,
        "gate": {
            "all_items_classified": not invalid,
            "invalid_item_ids": invalid,
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = refine(args.root.resolve(), args.output.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    if args.check and not manifest["gate"]["all_items_classified"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
