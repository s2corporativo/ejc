#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph", required=True, type=Path)
    ap.add_argument("--deleted", nargs="+", required=True)
    ns=ap.parse_args()
    g=json.loads(ns.graph.read_text(encoding="utf-8"))
    deleted={x.replace("\\","/").lstrip("./") for x in ns.deleted}
    ids_by_file={}
    for n in g.get("nodes",[]):
        f=(n.get("source_file") or "").replace("\\","/").lstrip("./")
        if f in deleted:
            ids_by_file.setdefault(f,set()).add(n.get("id"))
    blockers={}
    for e in g.get("links",[]):
        target=e.get("target")
        source_file=(e.get("source_file") or "").replace("\\","/").lstrip("./")
        for f,ids in ids_by_file.items():
            if target in ids and source_file and source_file not in deleted and source_file != f:
                blockers.setdefault(f,set()).add((source_file,e.get("relation","?")))
    if blockers:
        print("GRAPHIFY GATE: remoção bloqueada; há dependências externas:")
        for f,refs in sorted(blockers.items()):
            print(f"- {f}")
            for src,rel in sorted(refs)[:30]:
                print(f"    {rel}: {src}")
        return 2
    print(f"GRAPHIFY GATE: OK — {len(deleted)} arquivo(s) removido(s), sem dependências externas no grafo base.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
