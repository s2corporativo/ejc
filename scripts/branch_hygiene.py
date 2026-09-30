#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, datetime as dt, subprocess
from pathlib import Path

PROTECTED = (
    "main", "release/", "ops/", "backup/", "homologacao",
    "saneamento/vps-preservacao-", "saneamento/remover-legado-deploy-",
)

def git(*args: str, check: bool=True) -> str:
    p=subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if check and p.returncode:
        raise SystemExit(p.stderr.strip() or f"git {' '.join(args)} falhou")
    return p.stdout.strip()

def protected(name: str) -> bool:
    return any(name == p or name.startswith(p) for p in PROTECTED)

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--archive-after-days", type=int, default=45)
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--archive-old", action="store_true")
    ns=ap.parse_args()

    git("fetch", ns.remote, "--prune")
    main_ref=f"{ns.remote}/main"
    now=dt.datetime.now(dt.timezone.utc)
    rows=[]
    raw=git("for-each-ref", "--format=%(refname:short)|%(objectname)|%(committerdate:unix)", f"refs/remotes/{ns.remote}").splitlines()
    for line in raw:
        ref, sha, ts=line.split("|",2)
        name=ref.removeprefix(ns.remote+"/")
        if name in {"HEAD", ns.remote, "origin"} or " -> " in name:
            continue
        age=max(0,(now-dt.datetime.fromtimestamp(int(ts),dt.timezone.utc)).days)
        if protected(name):
            action="preserve"; unique=""
        else:
            unique=git("rev-list","--cherry-pick","--right-only","--count",f"{main_ref}...{ref}")
            n=int(unique)
            if n==0:
                action="delete-equivalent"
            elif age>ns.archive_after_days:
                action="archive-old-unique"
            else:
                action="review-consolidate"
        rows.append([name,sha,age,unique,action])

    if ns.manifest:
        ns.manifest.parent.mkdir(parents=True,exist_ok=True)
        with ns.manifest.open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            w.writerow(["branch","sha","age_days","unique_patches","action"])
            w.writerows(rows)

    if ns.apply:
        for name,sha,age,unique,action in rows:
            if action=="delete-equivalent":
                subprocess.run(["git","push",ns.remote,"--delete",name],check=True)
            elif action=="archive-old-unique" and ns.archive_old:
                tag=f"archive/branches/{now.date().isoformat()}/{name}"
                subprocess.run(["git","tag","-f",tag,sha],check=True)
                subprocess.run(["git","push",ns.remote,f"refs/tags/{tag}:refs/tags/{tag}"],check=True)
                subprocess.run(["git","push",ns.remote,"--delete",name],check=True)

    counts={}
    for *_,action in rows:
        counts[action]=counts.get(action,0)+1
    print(" ".join(f"{k}={v}" for k,v in sorted(counts.items())))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
