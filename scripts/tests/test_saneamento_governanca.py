#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def require(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")

approved=(ROOT/"infra/host-automation/ejc-deploy-approved.sh").read_text()
require('.deployed_sha' in approved, "deploy aprovado perdeu marcador canônico")
require('> "$APP_DIR/.deploy_last_sha"' not in approved, "fluxo ainda grava marcador legado")
require('rm -f -- "$APP_DIR/.deploy_last_sha"' in approved, "compatibilidade não limpa marcador legado")

wood=(ROOT/".woodpecker.yml").read_text()
require("graphify-guard:" in wood, "CI sem gate Graphify")
require("scripts/ci_graphify_guard.sh" in wood, "CI não executa wrapper Graphify")
graph_guard=(ROOT/"scripts/ci_graphify_guard.sh").read_text()
require("CI_PREV_COMMIT_SHA" in graph_guard, "Graphify push/main não usa commit anterior nativo do Woodpecker")

for rel in (
    "infra/host-automation/ejc-weekly-saneamento.sh",
    "infra/host-automation/systemd/ejc-weekly-saneamento.service",
    "infra/host-automation/systemd/ejc-weekly-saneamento.timer",
    "scripts/branch_hygiene.py",
    "scripts/graphify_dependency_gate.py",
    "docs/README.md",
):
    require((ROOT/rel).exists(), f"artefato de saneamento ausente: {rel}")

require(not (ROOT/"docs/EJC_PUBLICACAO_2026-09-23.md").exists(), "publicação histórica voltou à raiz docs")
require((ROOT/"docs/arquivo/historico-2026/EJC_PUBLICACAO_2026-09-23.md").exists(), "histórico não arquivado")

print("OK: governança de saneamento, deploy marker, Graphify, timer e docs canônicos")
