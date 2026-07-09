#!/usr/bin/env bash
set -euo pipefail

# EJC release guard
# Bloqueia regressões P0 antes de build/deploy:
# - marcadores reais de merge em código/configuração versionados;
# - arquivos .env/backup de segredo versionados;
# - arquivos temporários críticos que não devem entrar em release.

python3 - <<'PY'
from __future__ import annotations

import pathlib
import subprocess
import sys

IGNORE_PARTS = {
    ".git",
    ".venv",
    ".venv-codex",
    "node_modules",
    "site-packages",
    "dist",
    "coverage",
    "htmlcov",
    "__pycache__",
}

SCAN_SUFFIXES = {
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".sh",
    ".sql",
    ".txt",
}

SCAN_NAMES = {
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "requirements.txt",
    "package.json",
    "package-lock.json",
}

ENV_TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")
RESIDUE_PREFIXES = ("_QUARENTENA/", "_dead_code/", "_deploy_e2e1/", "graphify-out/")
RESIDUE_SUFFIXES = (".bak", ".old", ".orig")


def tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def ignored_path(path: pathlib.Path) -> bool:
    return any(part in IGNORE_PARTS for part in path.parts)


def is_env_template(path: str) -> bool:
    name = pathlib.PurePosixPath(path).name
    return name == ".env.example" or (name.startswith(".env.") and name.endswith(ENV_TEMPLATE_SUFFIXES))


def is_blocked_env(path: str) -> bool:
    posix = path.replace("\\", "/")
    name = pathlib.PurePosixPath(posix).name
    if is_env_template(posix):
        return False
    return (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith(".env.bak")
        or posix == "vps-tools/.env"
    )


def is_residue(path: str) -> bool:
    posix = path.replace("\\", "/")
    return posix.startswith(RESIDUE_PREFIXES) or posix.endswith(RESIDUE_SUFFIXES)


def should_scan_conflicts(path: pathlib.Path) -> bool:
    if ignored_path(path):
        return False
    return path.name in SCAN_NAMES or path.suffix in SCAN_SUFFIXES


def main() -> int:
    fail = False
    files = tracked_files()

    print("[EJC CI] Verificando marcadores de conflito de merge...")
    conflict_hits: list[str] = []
    for item in files:
        path = pathlib.Path(item)
        if not should_scan_conflicts(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            print(f"::warning::Nao foi possivel ler {item}: {exc}")
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if line.startswith("<<<<<<< ") or line.startswith(">>>>>>> "):
                conflict_hits.append(f"{item}:{line_no}:{line[:160]}")

    if conflict_hits:
        print("::error::Marcadores reais de conflito encontrados. Resolva semanticamente antes do merge.")
        for hit in conflict_hits:
            print(hit)
        fail = True

    print("[EJC CI] Verificando arquivos de ambiente/segredos versionados...")
    env_hits = [item for item in files if is_blocked_env(item)]
    if env_hits:
        print("::error::Arquivos de ambiente/segredo estao versionados. Remova da arvore e rotacione credenciais afetadas.")
        for hit in env_hits:
            print(hit)
        fail = True

    print("[EJC CI] Verificando backups/residuos criticos em release...")
    residue_hits = [item for item in files if is_residue(item)]
    if residue_hits:
        print("::warning::Residuos de desenvolvimento encontrados na arvore. Saneie antes do release final.")
        for hit in residue_hits:
            print(hit)

    if fail:
        print("[EJC CI] Gate P0 falhou.")
        return 1

    print("[EJC CI] Gate P0 aprovado.")
    return 0


raise SystemExit(main())
PY
