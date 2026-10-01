#!/usr/bin/env python3
"""Gate de congelamento da main durante certificação de release."""
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "release_candidate.json"


def validate(env: dict[str, str] | None = None) -> tuple[bool, str]:
    env = env or dict(os.environ)
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    required = {"schema_version", "release", "require_full_ci", "purpose", "freeze_main", "allowed_source_branch"}
    missing = required - set(data)
    if missing:
        return False, f"release_candidate sem campos: {sorted(missing)}"
    if not data["freeze_main"]:
        return True, "freeze desativado"
    if not data["require_full_ci"]:
        return False, "release congelada exige require_full_ci=true"

    event = env.get("CI_PIPELINE_EVENT", "")
    if not event:
        return True, "configuração válida fora do CI"
    if event == "pull_request":
        source = env.get("CI_COMMIT_SOURCE_BRANCH", "")
        if source != data["allowed_source_branch"]:
            return False, (
                f"main congelada para {data['release']}: PR de {source!r} bloqueada; "
                f"branch autorizada={data['allowed_source_branch']!r}"
            )
    return True, f"release freeze válido ({event})"


def main() -> int:
    ok, message = validate()
    print(("OK: " if ok else "FAIL: ") + message)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
