#!/usr/bin/env python3
"""Confere fontes públicas do catálogo e detecta alteração de conteúdo.

Executar em produção (onde o egress oficial e o banco estão disponíveis) e
persistir o manifesto fora do repositório, por exemplo em /var/lib/ejc. O
comando não promove automaticamente uma nova versão a fonte apta: apenas
registra hash, status e necessidade de revalidação humana.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

CATALOG = Path(__file__).with_name("fontes_publicas_iniciais.json")
ALLOWED_SUFFIXES = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br")


def _allowed(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host.endswith(ALLOWED_SUFFIXES) or host in {"gov.br", "jus.br"})


def _fetch(url: str, timeout: int) -> tuple[str, str, int]:
    req = Request(url, headers={"User-Agent": "EJC-FonteMonitor/1.0"})
    with urlopen(req, timeout=timeout) as response:  # noqa: S310 - allowlist checked above
        body = response.read()
        return hashlib.sha256(body).hexdigest(), response.headers.get_content_type(), response.status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    args = parser.parse_args(argv)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    previous = {}
    if args.out.exists():
        previous = json.loads(args.out.read_text(encoding="utf-8")).get("fontes", {})
    now = datetime.now(timezone.utc).isoformat()
    current: dict[str, dict] = {}
    changed = 0
    errors = 0
    for item in catalog["fontes"]:
        source_id, url = str(item["id"]), str(item["url"])
        record = {"id": source_id, "url": url, "titulo": item["titulo"], "status": "ok"}
        if not _allowed(url):
            record.update(status="erro", erro="dominio fora da allowlist")
            errors += 1
        else:
            try:
                sha256, content_type, status = _fetch(url, args.timeout)
                record.update(sha256=sha256, content_type=content_type, http_status=status)
                if previous.get(source_id, {}).get("sha256") not in (None, sha256):
                    record["mudou_desde_manifesto"] = True
                    record["revalidacao_humana"] = True
                    changed += 1
            except Exception as exc:  # rede indisponível não deve apagar o manifesto anterior
                record.update(status="erro", erro=type(exc).__name__)
                errors += 1
        current[source_id] = record
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"consultado_em": now, "fontes": current}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"fontes={len(current)} alteradas={changed} erros={errors} manifesto={args.out}")
    return 2 if errors or changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
