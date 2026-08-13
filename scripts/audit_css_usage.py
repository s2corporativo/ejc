"""Audita quais seletores de CSS globais paralelos são de fato usados no
frontend (consolidação 12/08/2026). Imprime para cada arquivo CSS o total de
seletores e quantos são referenciados no código TS/TSX."""
from __future__ import annotations
import os
import re
import sys
from collections import defaultdict

BASE = "/home/ubuntu/ejc/frontend/src"
CSS_DIR = f"{BASE}/styles"
CSS_FILES = [
    "fonts.css",
    "index.css",
    "site-system.css",
    "workspace-executive.css",
    "premium-shell.css",
    "premium-dashboard.css",
    "saas-ultra-v2.css",
    "saas-ultra-accessibility.css",
]

TS_EXTS = (".ts", ".tsx")


def ts_sources():
    for root, _, files in os.walk(BASE):
        if "node_modules" in root:
            continue
        for f in files:
            if f.endswith(TS_EXTS):
                yield os.path.join(root, f)


def classes_used(text: str) -> set[str]:
    return set(re.findall(r"className=\"([^\"]+)\"", text))


def main() -> int:
    # coletar todos os classNames usados no frontend
    usadas: set[str] = set()
    for p in ts_sources():
        with open(p, encoding="utf-8", errors="replace") as fh:
            conteudo = fh.read()
        for m in re.findall(r'className=\{?["`]([^"`]+)["`]', conteudo):
            for token in m.split():
                usadas.add(token)
        # Tailwind dinâmico: `ejc-` prefixo em template literals também
        for m in re.findall(r'["`]([a-z][\w-]*(?:\s+[a-z][\w-]*)*)["`]', conteudo):
            for token in m.split():
                if token.startswith(("ejc-", "sidebar-", "btn-", "card")):
                    usadas.add(token)

    total_usadas = 0
    for nome in CSS_FILES:
        path = f"{CSS_DIR}/{nome}"
        if not os.path.exists(path):
            print(f"{nome}: arquivo ausente")
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            css = fh.read()
        seletores = re.findall(r"\.([a-zA-Z_][\w-]*)", css)
        sel_counts = defaultdict(int)
        for s in seletores:
            sel_counts[s] += 1
        usados, nao_usados = [], []
        for s in sorted(sel_counts):
            (usados if s in usadas else nao_usados).append(f"{s}({sel_counts[s]})")
        total_usadas += len(usados)
        print(f"\n=== {nome}: {len(sel_counts)} seletores | usados={len(usados)} | não-usados={len(nao_usados)}")
        if nao_usados:
            print("  não-usados:", " ".join(nao_usados[:40]))
    print(f"\nTotal seletores CSS usados no frontend: {total_usadas}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
