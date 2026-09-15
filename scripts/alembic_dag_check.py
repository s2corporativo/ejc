#!/usr/bin/env python3
"""Valida estruturalmente o DAG de migrations Alembic, sem banco.

Contrato verificado (exit 1 em qualquer violação):
- cada arquivo define ``revision`` única (sem duplicatas);
- cada ``down_revision`` existe (inclusive tuplas de merge multiline);
- exatamente UM head (uma ponta de upgrade);
- nenhum ciclo no grafo (Kahn: nós processados == total).

O gate com banco (``alembic upgrade head`` + testes) permanece no backend-tests;
este passo é o contrato estrutural barato que roda antes de qualquer deploy.

Uso:
    python scripts/alembic_dag_check.py [--versions-dir backend/alembic/versions] [--print-head]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_RE_REVISION = re.compile(r"^revision(?::\s*str)?\s*=\s*[\"']([^\"']+)[\"']", re.M)
_RE_DOWN_START = re.compile(r"^down_revision(?::[^=\n]*)?\s*=\s*", re.M)


def _extrai_down(src: str) -> str | None:
    """Extrai o RHS de down_revision suportando tuplas multiline."""
    m = _RE_DOWN_START.search(src)
    if not m:
        return None
    buf: list[str] = []
    depth = 0
    for ch in src[m.end():]:
        buf.append(ch)
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth <= 0:
                break
        elif depth == 0 and ch == "\n":
            break
    return "".join(buf).strip()


def _parse_downs(raw: str | None) -> list[str]:
    if raw is None:
        return []
    limpo = re.sub(r"\s+", "", raw)
    if limpo in ("None", '""', "''", ""):
        return []
    return [x.strip("\"'") for x in limpo.replace("(", "").replace(")", "").split(",") if x.strip()]


def mapear(versions_dir: Path) -> tuple[dict[str, Path], dict[str, list[str]]]:
    revisions: dict[str, Path] = {}
    downs: dict[str, list[str]] = {}
    for f in sorted(versions_dir.glob("*.py")):
        src = f.read_text(encoding="utf-8", errors="replace")
        m = _RE_REVISION.search(src)
        if not m:
            raise SystemExit(f"ERRO: {f.name} não define revision")
        rev = m.group(1)
        if rev in revisions:
            raise SystemExit(f"ERRO: revision duplicada {rev!r} ({f.name} e {revisions[rev].name})")
        revisions[rev] = f
        downs[rev] = _parse_downs(_extrai_down(src))
    return revisions, downs


def validar(versions_dir: Path, quiet: bool = False) -> str:
    revisions, downs = mapear(versions_dir)
    if not revisions:
        raise SystemExit("ERRO: nenhuma migration encontrada")

    filhos: dict[str, list[str]] = {}
    for rev, ds in downs.items():
        for d in ds:
            if d not in revisions:
                raise SystemExit(f"ERRO: down_revision órfã {d!r} (referida por {rev!r})")
            filhos.setdefault(d, []).append(rev)

    heads = [r for r in revisions if r not in filhos]
    if len(heads) != 1:
        raise SystemExit(f"ERRO: esperado 1 head, encontrados {len(heads)}: {sorted(heads)}")

    # Kahn: se houver ciclo, nem todos os nós são processados.
    indeg = {r: len(downs[r]) for r in revisions}
    fila = [r for r in revisions if indeg[r] == 0]
    vistos = 0
    while fila:
        n = fila.pop()
        vistos += 1
        for c in filhos.get(n, []):
            indeg[c] -= 1
            if indeg[c] == 0:
                fila.append(c)
    if vistos != len(revisions):
        raise SystemExit("ERRO: ciclo no grafo de migrations")

    if quiet:
        return heads[0]
    print(f"OK: {len(revisions)} migrations, head único {heads[0]!r}")
    return heads[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--versions-dir", default="backend/alembic/versions")
    ap.add_argument("--print-head", action="store_true",
                    help="imprime APENAS o head revision id, sem resumo (modo máquina; "
                         "erros de validação continuam saindo em stderr com exit != 0)")
    args = ap.parse_args()
    head = validar(Path(args.versions_dir), quiet=args.print_head)
    if args.print_head:
        print(head)
    return 0


if __name__ == "__main__":
    sys.exit(main())
