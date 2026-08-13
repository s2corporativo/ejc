#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inventário de consolidação EJC — gera mapas para o Mapa da Verdade."""
import os
import re
import sys
from collections import Counter

ROOT = "/home/ubuntu/ejc"
FE = os.path.join(ROOT, "frontend/src")
BE = os.path.join(ROOT, "backend/app")

def find_endpoints(prefixes):
    """Extrai strings de endpoint usadas no frontend (sem interpolacao)."""
    pat = re.compile(r'["\'](/api)?/[a-z0-9_\-]+(/[a-z0-9_\-:$]+)*["\']')
    hits = Counter()
    files = []
    for base in ("lib", "pages", "components", "config", "stores", "contexts"):
        d = os.path.join(FE, base)
        if not os.path.isdir(d):
            continue
        for root, _, fs in os.walk(d):
            for f in fs:
                if not f.endswith((".ts", ".tsx")):
                    continue
                if "__tests__" in root:
                    continue
                path = os.path.join(root, f)
                try:
                    txt = open(path, encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                for m in pat.finditer(txt):
                    ep = m.group(0).strip('"').strip("'")
                    if "$" in ep or "{" in ep:
                        continue
                    hits[ep] += 1
    return hits

def backend_prefixes():
    """Lista prefixos de routers registrados em main.py."""
    main = open(os.path.join(BE, "main.py"), encoding="utf-8").read()
    pat = re.compile(r"include_router\((\w+)\.router[,\s]*prefix=(?:(\w+)\.|)(API)\)")
    # Captura mais simples: prefix=VALUE
    pat2 = re.compile(r"include_router\([^)]*prefix\s*=\s*\"([^\"]+)\"")
    return pat2.findall(main)

def css_consumers():
    """Verifica quais arquivos CSS globais são importados e por quem são usados."""
    main = open(os.path.join(FE, "main.tsx"), encoding="utf-8").read()
    imports = re.findall(r'import ["\']\./?[^"\']+\.css["\']', main)
    return imports

def big_files(maxlen=3000, ext=".tsx"):
    out = []
    for root, _, fs in os.walk(os.path.join(FE, "pages")):
        for f in fs:
            if not f.endswith(ext):
                continue
            p = os.path.join(root, f)
            n = sum(1 for _ in open(p, encoding="utf-8", errors="ignore"))
            if n >= maxlen:
                out.append((n, p))
    return sorted(out, reverse=True)

def backend_big(maxlen=40000):
    out = []
    for base in ("routers", "services"):
        d = os.path.join(BE, base)
        for f in os.listdir(d):
            if not f.endswith(".py"):
                continue
            p = os.path.join(d, f)
            s = os.path.getsize(p)
            if s >= maxlen:
                out.append((s, f"{base}/{f}"))
    return sorted(out, reverse=True)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "fe-ep"):
        eps = find_endpoints(None)
        print("=== FRONTEND ENDPOINTS (uso em código) ===")
        for ep, n in eps.most_common():
            print(f"{n:4d}  {ep}")
    if mode in ("all", "be-prefix"):
        print("=== BACKEND REGISTERED PREFIXES ===")
        for p in backend_prefixes():
            print(p)
    if mode in ("all", "css"):
        print("=== CSS GLOBAIS IMPORTADOS EM main.tsx ===")
        for c in css_consumers():
            print(c)
    if mode in ("all", "big"):
        print("=== FRONTEND PAGES >= 3000 linhas ===")
        for n, p in big_files():
            print(f"{n:5d}  {p}")
        print("=== BACKEND ARQUIVOS >= 40KB ===")
        for s, p in backend_big():
            print(f"{s:7d}  {p}")
