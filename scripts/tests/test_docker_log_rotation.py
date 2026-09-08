#!/usr/bin/env python3
"""Contrato estático do INF-02: nenhum serviço Docker canônico sem rotação."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = {
    # Valor = (anchor, exclusões explícitas). O contrato percorre TODOS os
    # serviços descobertos; adicionar serviço novo sem logging deve falhar.
    "docker-compose.yml": ("ejc-logging", set()),
    "infra/woodpecker/docker-compose.yml": ("woodpecker-logging", set()),
    "infra/monitoring/uptime-kuma/docker-compose.yml": ("kuma-logging", set()),
}



def service_blocks(text: str) -> dict[str, str]:
    lines = text.splitlines()
    in_services = False
    current: str | None = None
    blocks: dict[str, list[str]] = {}
    for line in lines:
        if line == "services:":
            in_services = True
            current = None
            continue
        if in_services and line and not line.startswith(" ") and not line.startswith("#"):
            break
        if not in_services:
            continue
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            current = match.group(1)
            blocks[current] = []
            continue
        if current is not None:
            blocks[current].append(line)
    return {name: "\n".join(lines) for name, lines in blocks.items()}


errors: list[str] = []
covered = 0
for rel, (anchor, exclusions) in CONFIGS.items():
    text = (ROOT / rel).read_text(encoding="utf-8")
    anchor_pattern = re.compile(
        rf"x-logging:\s*&{re.escape(anchor)}\n"
        r"\s+driver:\s+json-file\n"
        r"\s+options:\n"
        r"\s+max-size:\s+[\"\x27]?50m[\"\x27]?\n"
        r"\s+max-file:\s+[\"\x27]?5[\"\x27]?"
    )
    if not anchor_pattern.search(text):
        errors.append(f"{rel}: política 50m × 5 ausente ou alterada")
    blocks = service_blocks(text)
    if not blocks:
        errors.append(f"{rel}: nenhum serviço Docker descoberto")
        continue
    unknown_exclusions = exclusions - blocks.keys()
    if unknown_exclusions:
        errors.append(f"{rel}: exclusões não correspondem a serviços: {sorted(unknown_exclusions)}")
    for service, block in sorted(blocks.items()):
        if service in exclusions:
            continue
        covered += 1
        if f"logging: *{anchor}" not in block:
            errors.append(f"{rel}:{service}: logging não referencia *{anchor}")

if errors:
    raise SystemExit("\n".join(errors))
print(f"docker log rotation contract: {covered} serviços descobertos cobertos com json-file 50m × 5")
