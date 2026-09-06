#!/usr/bin/env python3
"""Gera o inventário arquitetural completo e auditável do EJC.

Escopo analisado, sem importar a aplicação e sem acessar banco/rede:
- páginas, componentes, rotas e chamadas de API do frontend;
- routers, endpoints, serviços, modelos, tabelas, classes e funções Python;
- funções TypeScript/TSX;
- dependências por importação, montagem de routers e referências a tabelas;
- classificação obrigatória: manter, consolidar, renomear, redirecionar,
  corrigir, desativar ou excluir após migração.

A classificação automática é conservadora. Regras explícitas ficam em
config/architecture_inventory_overrides.json e sempre prevalecem.
"""
from __future__ import annotations

import argparse
import ast
import csv
import fnmatch
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

CLASSIFICATIONS = (
    "manter",
    "consolidar",
    "renomear",
    "redirecionar",
    "corrigir",
    "desativar",
    "excluir após migração",
)
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
TEXT_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".md", ".json", ".yml", ".yaml"}
IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build", "coverage",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "graphify-out",
}


@dataclass(slots=True)
class InventoryItem:
    id: str
    kind: str
    name: str
    path: str
    line: int | None = None
    route: str | None = None
    method: str | None = None
    parent: str | None = None
    mounted: bool | None = None
    active: bool | None = None
    classification: str = "manter"
    classification_source: str = "default"
    confidence: str = "baixa"
    rationale: str = "Manutenção conservadora até revisão funcional documentada."
    dependencies: list[str] = field(default_factory=list)
    consumers: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    needs_review: bool = True


@dataclass(slots=True)
class OverrideRule:
    classification: str
    rationale: str
    confidence: str = "alta"
    kind: str | None = None
    path: str | None = None
    name: str | None = None
    route: str | None = None

    def matches(self, item: InventoryItem) -> bool:
        checks = (
            (self.kind, item.kind),
            (self.path, item.path),
            (self.name, item.name),
            (self.route, item.route or ""),
        )
        return all(pattern is None or fnmatch.fnmatchcase(value, pattern) for pattern, value in checks)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def stable_id(kind: str, path: str, name: str, line: int | None = None, route: str | None = None) -> str:
    raw = "|".join((kind, path, name, str(line or ""), route or ""))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return dotted_name(node.func)
    return ""


def python_imports(tree: ast.AST) -> list[str]:
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return sorted(values)


def extract_table_names(source: str) -> list[str]:
    names: set[str] = set()
    patterns = (
        r"\bFROM\s+([a-zA-Z_][\w.]*)",
        r"\bJOIN\s+([a-zA-Z_][\w.]*)",
        r"\bUPDATE\s+([a-zA-Z_][\w.]*)",
        r"\bINTO\s+([a-zA-Z_][\w.]*)",
        r"\bTABLE\s+([a-zA-Z_][\w.]*)",
    )
    for pattern in patterns:
        for value in re.findall(pattern, source, flags=re.IGNORECASE):
            names.add(value.split(".")[-1].lower())
    return sorted(names)


def router_mounts(root: Path) -> tuple[str, set[str], dict[str, list[str]]]:
    main_path = root / "backend/app/main.py"
    source = safe_read(main_path) if main_path.exists() else ""
    mounted_modules: set[str] = set()
    mounted_attrs: dict[str, list[str]] = defaultdict(list)
    for module, attr in re.findall(r"app\.include_router\(\s*([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)", source):
        mounted_modules.add(module)
        mounted_attrs[module].append(attr)
    return source, mounted_modules, dict(mounted_attrs)


def router_prefixes(tree: ast.AST) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or dotted_name(value.func).split(".")[-1] != "APIRouter":
            continue
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node.target, ast.expr):
            targets = [node.target]
        prefix = ""
        for kw in value.keywords:
            if kw.arg == "prefix":
                prefix = literal_string(kw.value) or ""
        for target in targets:
            if isinstance(target, ast.Name):
                result[target.id] = prefix
    return result


def python_inventory(root: Path) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    _, mounted_modules, mounted_attrs = router_mounts(root)
    backend = root / "backend/app"
    if not backend.exists():
        return items

    for path in sorted(backend.rglob("*.py")):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        relative = rel(root, path)
        source = safe_read(path)
        try:
            tree = ast.parse(source, filename=relative)
        except SyntaxError as exc:
            items.append(InventoryItem(
                id=stable_id("python_parse_error", relative, path.name, exc.lineno),
                kind="python_parse_error",
                name=path.name,
                path=relative,
                line=exc.lineno,
                classification="corrigir",
                classification_source="parser",
                confidence="alta",
                rationale=f"Arquivo Python não pôde ser analisado por AST: {exc.msg}.",
                needs_review=False,
            ))
            continue

        imports = python_imports(tree)
        tables = extract_table_names(source)
        stem = path.stem
        is_router_file = "/routers/" in f"/{relative}" or relative.endswith("/router.py")
        is_service_file = "/services/" in f"/{relative}"
        is_model_file = "/models/" in f"/{relative}"
        mounted = stem in mounted_modules if is_router_file else None

        file_kind = "python_module"
        if is_router_file:
            file_kind = "router"
        elif is_service_file:
            file_kind = "service"
        elif is_model_file:
            file_kind = "model_file"

        items.append(InventoryItem(
            id=stable_id(file_kind, relative, stem),
            kind=file_kind,
            name=stem,
            path=relative,
            mounted=mounted,
            active=mounted if is_router_file else True,
            dependencies=imports,
            tables=tables,
            metadata={"mounted_router_attributes": mounted_attrs.get(stem, [])},
        ))

        prefixes = router_prefixes(tree)

        class Visitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.stack: list[str] = []

            def visit_ClassDef(self, node: ast.ClassDef) -> Any:
                qualified = ".".join((*self.stack, node.name))
                table_name: str | None = None
                for stmt in node.body:
                    if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                        targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                        if any(isinstance(target, ast.Name) and target.id == "__tablename__" for target in targets):
                            table_name = literal_string(stmt.value)
                            break
                kind = "table" if table_name else "class"
                item_name = table_name or qualified
                items.append(InventoryItem(
                    id=stable_id(kind, relative, item_name, node.lineno),
                    kind=kind,
                    name=item_name,
                    path=relative,
                    line=node.lineno,
                    parent=stem,
                    mounted=mounted if is_router_file else None,
                    active=True,
                    dependencies=[dotted_name(base) for base in node.bases if dotted_name(base)],
                    tables=[table_name] if table_name else tables,
                    metadata={"python_class": qualified} if table_name else {},
                ))
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> Any:
                qualified = ".".join((*self.stack, node.name))
                endpoints: list[tuple[str, str, str]] = []
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    decorator_name = dotted_name(decorator.func)
                    parts = decorator_name.split(".")
                    if len(parts) < 2 or parts[-1].lower() not in HTTP_METHODS:
                        continue
                    router_var = parts[-2]
                    route = literal_string(decorator.args[0]) if decorator.args else ""
                    if route is None:
                        route = "<dinâmica>"
                    prefix = prefixes.get(router_var, "")
                    full_route = f"/api{prefix}{route}".replace("//", "/")
                    endpoints.append((parts[-1].upper(), full_route, router_var))

                if endpoints:
                    for method, route, router_var in endpoints:
                        endpoint_mounted = mounted and (
                            not mounted_attrs.get(stem) or router_var in mounted_attrs.get(stem, [])
                        )
                        items.append(InventoryItem(
                            id=stable_id("endpoint", relative, qualified, node.lineno, f"{method} {route}"),
                            kind="endpoint",
                            name=qualified,
                            path=relative,
                            line=node.lineno,
                            route=route,
                            method=method,
                            parent=stem,
                            mounted=endpoint_mounted,
                            active=endpoint_mounted,
                            dependencies=imports,
                            tables=tables,
                            metadata={"router_variable": router_var, "async": isinstance(node, ast.AsyncFunctionDef)},
                        ))
                else:
                    items.append(InventoryItem(
                        id=stable_id("function", relative, qualified, node.lineno),
                        kind="function",
                        name=qualified,
                        path=relative,
                        line=node.lineno,
                        parent=stem,
                        active=True,
                        dependencies=imports,
                        tables=tables,
                        metadata={"async": isinstance(node, ast.AsyncFunctionDef)},
                    ))
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
                return self._visit_function(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
                return self._visit_function(node)

        Visitor().visit(tree)
    return items


def frontend_imports(source: str) -> list[str]:
    values = set(re.findall(r"(?:from\s+|import\s*\()?[\"']([^\"']+)[\"']", source))
    return sorted(value for value in values if value.startswith(".") or value.startswith("@/") or "/" in value)


def frontend_api_calls(source: str) -> list[str]:
    calls: set[str] = set()
    method_pattern = re.compile(
        r"\b(?:api|axios)\.(?:get|post|put|patch|delete)\s*\(\s*([`\"'])(.+?)\1",
        re.DOTALL,
    )
    for match in method_pattern.finditer(source):
        value = re.sub(r"\$\{[^}]+\}", "{param}", match.group(2))
        if value.startswith("/"):
            calls.add(value)
    for value in re.findall(r"[\"'`](/(?:api/|v1/)[^\"'`\s?]+)", source):
        calls.add(re.sub(r"\$\{[^}]+\}", "{param}", value))
    return sorted(calls)


def parse_module_registry(source: str, path: str) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    object_pattern = re.compile(r"\{(?P<body>\s*key:\s*[\"'][^}]+?)\n\s*\},", re.DOTALL)
    for match in object_pattern.finditer(source):
        body = match.group("body")
        key_m = re.search(r"\bkey:\s*[\"']([^\"']+)", body)
        route_m = re.search(r"\bpath:\s*[\"']([^\"']+)", body)
        if not key_m or not route_m:
            continue
        label_m = re.search(r"\blabel:\s*[\"']([^\"']+)", body)
        component_m = re.search(r"\bcomponent:\s*([A-Za-z_$][\w$]*)", body)
        status_m = re.search(r"\bstatus:\s*[\"']([^\"']+)", body)
        nav_m = re.search(r"\bshowInNav:\s*(true|false)", body)
        line = source[:match.start()].count("\n") + 1
        route = route_m.group(1)
        items.append(InventoryItem(
            id=stable_id("frontend_route", path, key_m.group(1), line, route),
            kind="frontend_route",
            name=key_m.group(1),
            path=path,
            line=line,
            route=route,
            active=status_m is None or status_m.group(1) != "disabled",
            metadata={
                "label": label_m.group(1) if label_m else None,
                "component": component_m.group(1) if component_m else None,
                "status": status_m.group(1) if status_m else "active",
                "show_in_nav": None if nav_m is None else nav_m.group(1) == "true",
            },
        ))
    return items


def parse_legacy_redirects(source: str, path: str) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    pattern = re.compile(
        r"\{\s*from:\s*[\"']([^\"']+)[\"']\s*,\s*to:\s*[\"']([^\"']+)[\"'](?:\s*,\s*reason:\s*[\"']([^\"']*)[\"'])?\s*\}",
        re.DOTALL,
    )
    for match in pattern.finditer(source):
        line = source[:match.start()].count("\n") + 1
        items.append(InventoryItem(
            id=stable_id("redirect", path, match.group(1), line, match.group(2)),
            kind="redirect",
            name=match.group(1),
            path=path,
            line=line,
            route=match.group(1),
            active=True,
            classification="redirecionar",
            classification_source="source",
            confidence="alta",
            rationale=f"Alias histórico redirecionado para {match.group(2)}.",
            metadata={"target": match.group(2), "reason": match.group(3) or ""},
            needs_review=False,
        ))
    return items


def parse_app_routes(source: str, path: str) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    for match in re.finditer(r"<Route\b[^>]*\bpath=[\"']([^\"']+)[\"']", source, flags=re.DOTALL):
        route = match.group(1)
        line = source[:match.start()].count("\n") + 1
        items.append(InventoryItem(
            id=stable_id("frontend_route", path, route, line, route),
            kind="frontend_route",
            name=route,
            path=path,
            line=line,
            route=route,
            active=True,
            metadata={"source": "App.tsx"},
        ))
    return items


def frontend_inventory(root: Path) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    frontend = root / "frontend/src"
    if not frontend.exists():
        return items

    for path in sorted(frontend.rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        relative = rel(root, path)
        source = safe_read(path)
        imports = frontend_imports(source)
        api_calls = frontend_api_calls(source)

        if "/pages/" in f"/{relative}" and path.suffix in {".tsx", ".jsx"}:
            items.append(InventoryItem(
                id=stable_id("page", relative, path.stem),
                kind="page",
                name=path.stem,
                path=relative,
                active=True,
                dependencies=imports,
                consumers=api_calls,
                metadata={"api_calls": api_calls},
            ))
        elif "/components/" in f"/{relative}" and path.suffix in {".tsx", ".jsx"}:
            items.append(InventoryItem(
                id=stable_id("component", relative, path.stem),
                kind="component",
                name=path.stem,
                path=relative,
                active=True,
                dependencies=imports,
                consumers=api_calls,
                metadata={"api_calls": api_calls},
            ))

        function_patterns = (
            re.compile(r"\b(?:export\s+default\s+|export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("),
            re.compile(r"\b(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^;=]*\)\s*=>"),
        )
        seen: set[tuple[str, int]] = set()
        for pattern in function_patterns:
            for match in pattern.finditer(source):
                name = match.group(1)
                line = source[:match.start()].count("\n") + 1
                if (name, line) in seen:
                    continue
                seen.add((name, line))
                items.append(InventoryItem(
                    id=stable_id("frontend_function", relative, name, line),
                    kind="frontend_function",
                    name=name,
                    path=relative,
                    line=line,
                    parent=path.stem,
                    active=True,
                    dependencies=imports,
                    consumers=api_calls,
                ))

        if relative == "frontend/src/config/moduleRegistry.tsx":
            items.extend(parse_module_registry(source, relative))
            items.extend(parse_legacy_redirects(source, relative))
        if relative == "frontend/src/App.tsx":
            items.extend(parse_app_routes(source, relative))
    return items


def load_overrides(root: Path) -> list[OverrideRule]:
    path = root / "config/architecture_inventory_overrides.json"
    if not path.exists():
        return []
    data = json.loads(safe_read(path))
    rules: list[OverrideRule] = []
    for raw in data.get("rules", []):
        classification = raw["classification"]
        if classification not in CLASSIFICATIONS:
            raise ValueError(f"Classificação inválida no override: {classification}")
        rules.append(OverrideRule(
            classification=classification,
            rationale=raw["rationale"],
            confidence=raw.get("confidence", "alta"),
            kind=raw.get("kind"),
            path=raw.get("path"),
            name=raw.get("name"),
            route=raw.get("route"),
        ))
    return rules


def normalized_family(item: InventoryItem) -> str:
    value = Path(item.path).stem.lower()
    value = re.sub(r"(?:_router|_service)$", "", value)
    value = re.sub(r"_(?:v|version)?\d+$", "", value)
    value = re.sub(r"(?:modern|luxury|legacy|old|novo|nova)$", "", value)
    return value.strip("_-")


def duplicate_families(items: Iterable[InventoryItem]) -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    eligible = {"router", "service", "page", "component", "table", "model_file"}
    for item in items:
        if item.kind not in eligible:
            continue
        family = normalized_family(item)
        if family:
            grouped[family].add(item.path)
    return {family: sorted(paths) for family, paths in grouped.items() if len(paths) > 1}


def classify(items: list[InventoryItem], overrides: list[OverrideRule]) -> None:
    duplicates = duplicate_families(items)
    duplicate_paths = {path for paths in duplicates.values() for path in paths}

    parent_classification: dict[tuple[str, str], tuple[str, str, str]] = {}
    for item in items:
        if item.kind in {"router", "service", "page", "component", "model_file", "python_module"}:
            parent_classification[(item.path, item.name)] = (
                item.classification, item.classification_source, item.rationale
            )

    for item in items:
        if item.classification_source == "source":
            continue

        matched = next((rule for rule in overrides if rule.matches(item)), None)
        if matched:
            item.classification = matched.classification
            item.classification_source = "override"
            item.confidence = matched.confidence
            item.rationale = matched.rationale
            item.needs_review = False
            continue

        lower_path = item.path.lower()
        lower_name = item.name.lower()
        if item.kind in {"router", "endpoint"} and item.mounted is False:
            item.classification = "desativar"
            item.classification_source = "mount-analysis"
            item.confidence = "alta"
            item.rationale = "Router/endpoint não montado no ponto de entrada FastAPI atual."
            item.needs_review = True
        elif any(token in lower_path for token in ("/legacy", "_legacy", "/old/", "_old", "/backup/", "_backup")):
            item.classification = "excluir após migração"
            item.classification_source = "naming-heuristic"
            item.confidence = "média"
            item.rationale = "Nome indica implementação histórica; excluir somente após comprovar ausência de consumidores."
            item.needs_review = True
        elif item.path in duplicate_paths and item.kind in {"router", "service", "page", "component", "model_file"}:
            item.classification = "consolidar"
            item.classification_source = "duplicate-family"
            item.confidence = "média"
            item.rationale = "Pertence a família com versões ou responsabilidades potencialmente sobrepostas."
            item.needs_review = True
        elif item.kind == "python_parse_error":
            item.classification = "corrigir"
            item.classification_source = "parser"
            item.confidence = "alta"
            item.needs_review = False
        elif item.kind == "redirect":
            item.classification = "redirecionar"
            item.classification_source = "source"
            item.confidence = "alta"
            item.needs_review = False
        else:
            item.classification = "manter"
            item.classification_source = "conservative-default"
            item.confidence = "baixa"
            item.rationale = "Mantido por segurança até revisão de uso, contrato, dados e consumidores."
            item.needs_review = True

    # Funções e endpoints herdam decisões explícitas do arquivo pai quando aplicável.
    by_path = defaultdict(list)
    for item in items:
        by_path[item.path].append(item)
    for path_items in by_path.values():
        parents = [
            item for item in path_items
            if item.kind in {"router", "service", "page", "component", "model_file", "python_module"}
            and item.classification_source == "override"
        ]
        if not parents:
            continue
        parent = parents[0]
        for item in path_items:
            if item.kind in {"endpoint", "function", "frontend_function", "class"} and item.classification_source == "conservative-default":
                item.classification = parent.classification
                item.classification_source = "parent-override"
                item.confidence = parent.confidence
                item.rationale = f"Herda a decisão explícita do arquivo {parent.path}: {parent.rationale}"
                item.needs_review = parent.needs_review


def link_consumers(items: list[InventoryItem]) -> None:
    endpoints = [item for item in items if item.kind == "endpoint" and item.route]
    front_files = [item for item in items if item.kind in {"page", "component"}]
    for endpoint in endpoints:
        normalized = re.sub(r"\{[^}]+\}", "", endpoint.route or "").rstrip("/")
        consumers: set[str] = set(endpoint.consumers)
        if normalized:
            for front in front_files:
                calls = front.metadata.get("api_calls", [])
                if any(normalized in call or call.rstrip("/") in normalized for call in calls):
                    consumers.add(front.path)
        endpoint.consumers = sorted(consumers)


def source_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    included_roots = (root / "backend/app", root / "frontend/src", root / "backend/alembic/versions")
    for base in included_roots:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in TEXT_EXTENSIONS:
                continue
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            digest.update(rel(root, path).encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def write_csv(path: Path, items: list[InventoryItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id", "kind", "name", "path", "line", "method", "route", "parent",
        "mounted", "active", "classification", "classification_source", "confidence",
        "needs_review", "rationale", "dependencies", "consumers", "tables", "metadata",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in items:
            raw = asdict(item)
            raw["dependencies"] = " | ".join(item.dependencies)
            raw["consumers"] = " | ".join(item.consumers)
            raw["tables"] = " | ".join(item.tables)
            raw["metadata"] = json.dumps(item.metadata, ensure_ascii=False, sort_keys=True)
            writer.writerow(raw)


def markdown_table(items: list[InventoryItem], limit: int | None = None) -> list[str]:
    lines = [
        "| Tipo | Item | Arquivo/rota | Classificação | Fonte | Revisão |",
        "|---|---|---|---|---|---|",
    ]
    selected = items if limit is None else items[:limit]
    for item in selected:
        location = item.route or item.path
        if item.line:
            location = f"{location}:{item.line}"
        lines.append(
            f"| {item.kind} | `{item.name}` | `{location}` | **{item.classification}** | "
            f"{item.classification_source} | {'sim' if item.needs_review else 'não'} |"
        )
    return lines


def write_markdown(path: Path, items: list[InventoryItem], fingerprint: str) -> None:
    counts_kind = Counter(item.kind for item in items)
    counts_class = Counter(item.classification for item in items)
    counts_source = Counter(item.classification_source for item in items)
    duplicates = duplicate_families(items)
    review = [item for item in items if item.needs_review]
    unmounted = [item for item in items if item.kind == "router" and item.mounted is False]
    endpoints = [item for item in items if item.kind == "endpoint"]
    routes = [item for item in items if item.kind == "frontend_route"]
    tables = [item for item in items if item.kind == "table"]
    services = [item for item in items if item.kind == "service"]
    pages = [item for item in items if item.kind == "page"]

    lines = [
        "# Inventário Arquitetural EJC — Fase 0",
        "",
        f"Gerado em: {datetime.now(timezone.utc).isoformat()}",
        f"Fingerprint das fontes: `{fingerprint}`",
        "",
        "> Este inventário é descritivo e conservador. Nenhuma exclusão deve ocorrer apenas por heurística. ",
        "> Itens marcados para exclusão exigem migração, telemetria, busca de consumidores e plano de rollback.",
        "",
        "## Cobertura",
        "",
        f"- Itens totais: **{len(items)}**",
        f"- Páginas: **{len(pages)}**",
        f"- Rotas frontend: **{len(routes)}**",
        f"- Endpoints backend: **{len(endpoints)}**",
        f"- Serviços backend: **{len(services)}**",
        f"- Tabelas ORM detectadas: **{len(tables)}**",
        f"- Routers não montados: **{len(unmounted)}**",
        f"- Itens que ainda exigem revisão humana: **{len(review)}**",
        "",
        "## Classificação",
        "",
        "| Classificação | Quantidade |",
        "|---|---:|",
    ]
    lines.extend(f"| {classification} | {counts_class.get(classification, 0)} |" for classification in CLASSIFICATIONS)
    lines.extend(["", "## Tipos inventariados", "", "| Tipo | Quantidade |", "|---|---:|"])
    lines.extend(f"| {kind} | {count} |" for kind, count in sorted(counts_kind.items()))
    lines.extend(["", "## Origem das classificações", "", "| Origem | Quantidade |", "|---|---:|"])
    lines.extend(f"| {source} | {count} |" for source, count in sorted(counts_source.items()))

    lines.extend(["", "## Famílias candidatas à consolidação", ""])
    if duplicates:
        for family, paths in sorted(duplicates.items()):
            lines.append(f"### `{family}`")
            lines.extend(f"- `{value}`" for value in paths)
            lines.append("")
    else:
        lines.append("Nenhuma família detectada pela normalização automática.")

    sections = (
        ("Páginas", pages),
        ("Rotas frontend", routes),
        ("Endpoints backend", endpoints),
        ("Serviços", services),
        ("Tabelas", tables),
        ("Routers não montados", unmounted),
    )
    for title, section_items in sections:
        lines.extend(["", f"## {title}", ""])
        lines.extend(markdown_table(sorted(section_items, key=lambda item: (item.path, item.line or 0))))

    lines.extend([
        "",
        "## Critério de remoção",
        "",
        "Um item classificado como `excluir após migração` somente pode ser removido após:",
        "",
        "1. comprovação de ausência de consumidores frontend, scripts, jobs, webhooks e integrações;",
        "2. período de telemetria ou logs sem uso;",
        "3. alias/redirecionamento quando houver rota pública ou favorita histórica;",
        "4. migração/backfill de dados quando houver persistência;",
        "5. testes de regressão e rollback documentado;",
        "6. aprovação explícita no PR de remoção.",
        "",
        "## Arquivos complementares",
        "",
        "- `architecture_inventory.json`: representação integral e estruturada;",
        "- `architecture_inventory.csv`: planilha única para triagem e filtros;",
        "- `classification_review.csv`: somente itens que exigem revisão humana;",
        "- `duplicate_families.json`: famílias candidatas à consolidação;",
        "- `manifest.json`: contagens, fingerprint e resultado do gate.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate(root: Path, output: Path) -> dict[str, Any]:
    items = python_inventory(root) + frontend_inventory(root)
    overrides = load_overrides(root)
    classify(items, overrides)
    link_consumers(items)
    items.sort(key=lambda item: (item.kind, item.path, item.line or 0, item.name, item.route or ""))
    fingerprint = source_fingerprint(root)
    output.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_fingerprint": fingerprint,
        "allowed_classifications": list(CLASSIFICATIONS),
        "items": [asdict(item) for item in items],
    }
    (output / "architecture_inventory.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_csv(output / "architecture_inventory.csv", items)
    write_csv(output / "classification_review.csv", [item for item in items if item.needs_review])
    (output / "duplicate_families.json").write_text(
        json.dumps(duplicate_families(items), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_markdown(output / "README.md", items, fingerprint)

    counts = {
        "total": len(items),
        "by_kind": dict(sorted(Counter(item.kind for item in items).items())),
        "by_classification": dict(sorted(Counter(item.classification for item in items).items())),
        "needs_review": sum(item.needs_review for item in items),
        "unmounted_routers": sum(item.kind == "router" and item.mounted is False for item in items),
        "source_fingerprint": fingerprint,
    }
    invalid = [item.id for item in items if item.classification not in CLASSIFICATIONS]
    manifest = {
        **counts,
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
    parser.add_argument("--root", type=Path, default=repository_root())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="Retorna erro se houver item sem classificação válida.")
    args = parser.parse_args()

    root = args.root.resolve()
    output = (args.output or root / "docs/auditoria/inventory").resolve()
    manifest = generate(root, output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    if args.check and not manifest["gate"]["all_items_classified"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
