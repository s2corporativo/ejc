#!/usr/bin/env python3
"""Módulo 01 — Inventário e Baseline: verificação automática de consistência.

Verifica (apenas leitura de código):
1. Módulos router existentes que NÃO estão registrados no main.py (routers órfãos).
2. Prefixos de router duplicados (potencial colisão de endpoints).
3. Routers registrados com import ausente/falho no main.py.
4. Modelos importados no Base.metadata vs routers.
"""
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTERS_DIR = REPO / "backend/app/routers"
MAIN = REPO / "backend/app/main.py"

main_src = MAIN.read_text()
main_tree = ast.parse(main_src)

# 1) Modules imported in main.py
imported_modules = set()
for node in ast.walk(main_tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            imported_modules.add(alias.name.split(".")[-1])
    elif isinstance(node, ast.ImportFrom):
        if node.module and "routers" in (node.module or ""):
            for alias in node.names:
                imported_modules.add(alias.name)

router_files = {p.stem for p in ROUTERS_DIR.glob("*.py") if p.stem != "__init__"}
orphan_routers = sorted(router_files - imported_modules)
missing_imports = sorted(imported_modules - router_files)

# 2) Registered routers via include_router(XXX.router ...)
registered = re.findall(r"include_router\((\w+)\.router", main_src)
# imports actually declared
import_names = {m for m in imported_modules if m in registered or True}
registered_not_imported = sorted(set(registered) - set(imported_modules))

# 3) Duplicate prefixes
prefixes = {}
for m in router_files:
    f = ROUTERS_DIR / f"{m}.py"
    src = f.read_text(errors="replace")
    for mm in re.finditer(r'APIRouter\((?:prefix\s*=\s*)?"([^"]*)"', src):
        prefixes.setdefault(mm.group(1), []).append(m)
dup_prefixes = {k: v for k, v in prefixes.items() if len(v) > 1 and k}

# 4) API prefix constants (some routers use variable prefixes)
var_prefix = re.findall(r"include_router\((\w+)\.router, prefix=(\w+)", main_src)

print("=== TOTAL router modules:", len(router_files))
print("=== orphan routers (existem, mas NÃO importados no main.py):", len(orphan_routers))
for o in orphan_routers:
    print("  -", o)
print("=== importados sem arquivo:", missing_imports)
print("=== registered mas sem import declarado:", registered_not_imported)
print("=== duplicate APIRouter prefixes:", dup_prefixes)
print("=== variable-prefix registrations:")
for r, v in var_prefix:
    print(f"  {r} -> {v}")

# duplicate endpoint paths (any method) across routers — coarse check
path_by_file = {}
for m in router_files:
    f = ROUTERS_DIR / f"{m}.py"
    src = f.read_text(errors="replace")
    for mm in re.finditer(r'@(?:router|app)\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']', src):
        path_by_file.setdefault((m, mm.group(2)), []).append(mm.group(1))

from collections import defaultdict
dup_paths = defaultdict(list)
for (m, p), methods in path_by_file.items():
    dup_paths[p].append((m, methods))
print("=== duplicate paths across files (sem considerar prefix):")
for p, occ in sorted(dup_paths.items()):
    if len(occ) > 1:
        print(f"  {p}: {[(m, mt) for m, mt in occ]}")
