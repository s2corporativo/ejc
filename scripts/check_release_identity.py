#!/usr/bin/env python3
"""Prova determinística da identidade de uma release EJC."""
from __future__ import annotations
import argparse
import json
import re
import http.client
from urllib.parse import urlsplit
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")

def validate_identity(*, expected: str, marker: str | None, local_commit: str,
                      public_commit: str, require_marker: bool = True) -> list[str]:
    errors: list[str] = []
    if not SHA_RE.fullmatch(expected):
        errors.append(f"expected_sha inválido: {expected!r}")
    if require_marker and marker != expected:
        errors.append(f".deployed_sha divergente: {marker!r} != {expected}")
    if local_commit != expected:
        errors.append(f"health local divergente: {local_commit!r} != {expected}")
    if public_commit != expected:
        errors.append(f"health público divergente: {public_commit!r} != {expected}")
    return errors

def _health_commit(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("health URL precisa usar http/https com host explícito")
    if parsed.username or parsed.password:
        raise ValueError("credenciais embutidas não são permitidas na health URL")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    connection_cls = (
        http.client.HTTPSConnection if parsed.scheme == "https"
        else http.client.HTTPConnection
    )
    conn = connection_cls(parsed.hostname, port=port, timeout=15)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    try:
        conn.request("GET", path, headers={"Accept": "application/json"})
        response = conn.getresponse()
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"health URL retornou HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        conn.close()
    return str(payload.get("commit", "")).strip()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", required=True)
    parser.add_argument("--app-dir", default="/opt/ejc")
    parser.add_argument("--local-url", default="http://127.0.0.1:8000/api/health")
    parser.add_argument("--public-url", default="https://ejc.depaulateixeira.adv.br/api/health")
    parser.add_argument("--skip-marker", action="store_true")
    args = parser.parse_args()

    marker_path = Path(args.app_dir) / ".deployed_sha"
    marker = None
    if not args.skip_marker and marker_path.exists():
        marker = marker_path.read_text(encoding="utf-8").strip()

    local_commit = _health_commit(args.local_url)
    public_commit = _health_commit(args.public_url)
    errors = validate_identity(
        expected=args.expected,
        marker=marker,
        local_commit=local_commit,
        public_commit=public_commit,
        require_marker=not args.skip_marker,
    )
    result = {
        "status": "ok" if not errors else "error",
        "expected": args.expected,
        "marker": marker,
        "local_commit": local_commit,
        "public_commit": public_commit,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 2

if __name__ == "__main__":
    raise SystemExit(main())
