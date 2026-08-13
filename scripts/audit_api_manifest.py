#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o manifesto de endpoints do backend (método + path) para auditoria
semântica de duplicações. Lê os routers em backend/app/routers/*.py e extrai
as rotas registradas via @router.<method>(...)."""
import os
import re
import sys
from collections import defaultdict

ROOT = "/home/ubuntu/ejc/backend/app"
ROUTERS = os.path.join(ROOT, "routers")

PAT = re.compile(r'@router\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']')

def scan():
    manifest = defaultdict(list)
    for f in sorted(os.listdir(ROUTERS)):
        if not f.endswith(".py"):
            continue
        txt = open(os.path.join(ROUTERS, f), encoding="utf-8", errors="ignore").read()
        for m in PAT.finditer(txt):
            method, path = m.group(1).upper(), m.group(2)
            manifest[(method, f)].append(path)
    return manifest

def prefix_of(manifest, fname):
    """Tenta achar o prefix do router no próprio arquivo."""
    txt = open(os.path.join(ROUTERS, fname), encoding="utf-8", errors="ignore").read()
    m = re.search(r'prefix\s*=\s*["\']([^"\']+)["\']', txt)
    return m.group(1) if m else ""

if __name__ == "__main__":
    manifest = scan()
    # Agrupar por prefixo
    by_prefix = defaultdict(lambda: defaultdict(int))
    for (method, fname), paths in manifest.items():
        px = prefix_of(manifest, fname)
        key = px or "(sem prefixo)"
        for p in paths:
            by_prefix[key][(method, p)] += 1
    out = []
    for px in sorted(by_prefix):
        entries = sorted(by_prefix[px])
        out.append(f"PREFIXO: {px} | {len(entries)} rotas (arquivo: {', '.join(sorted({k for k in by_prefix if True}) if False else '—')})")
    # Simples: listar (prefix, method, path, count) com duplicacoes
    dup = []
    for px, items in by_prefix.items():
        for (method, path), n in items.items():
            if n > 1:
                dup.append(f"{px}{path} [{method}] x{n}")
    print("=== DUPLICACOES LITERAIS (mesmo prefixo+metodo+path) ===")
    print("\n".join(dup) if dup else "(nenhuma)")
    print("\n=== RESUMO POR PREFIXO (qtd de rotas) ===")
    for px in sorted(by_prefix, key=lambda x: -len(by_prefix[x])):
        print(f"{len(by_prefix[px]):4d}  {px}")
