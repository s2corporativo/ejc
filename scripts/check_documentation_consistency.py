#!/usr/bin/env python3
"""Valida referências canônicas e drift básico da documentação do EJC.

O gate é deliberadamente determinístico e não acessa rede. Ele verifica somente
as fontes operacionais canônicas, evitando que documentos históricos arquivados
bloqueiem a CI por links intencionalmente antigos.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

REQUIRED_WORKFLOW_NAMES = {
    "CI",
    "EJC Release Gate",
    "Continuity and UI Gates",
    "Architecture Inventory — Phase 0",
}

MANUAL_METRIC_RE = re.compile(
    r"\b\d+[\d.,]*\s+(?:routers?|services?|p[aá]ginas?|pages?|tabelas?|tables?)\b",
    re.IGNORECASE,
)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
CANONICAL_PATH_RE = re.compile(r"^-\s+`([^`]+\.md)`\s+—", re.MULTILINE)
WORKFLOW_NAME_RE = re.compile(r"^name:\s*[\"']?(.+?)[\"']?\s*$", re.MULTILINE)


def _relative_link_target(document: Path, raw_target: str, root: Path) -> Path | None:
    target = raw_target.strip().split("#", 1)[0].strip()
    if not target or target.startswith(("http://", "https://", "mailto:", "tel:", "#")):
        return None
    target = unquote(target)
    candidate = (document.parent / target).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return candidate
    return candidate


def _canonical_documents(root: Path, readme_text: str) -> list[Path]:
    documents = [root / "README.md"]
    for relative in CANONICAL_PATH_RE.findall(readme_text):
        documents.append(root / relative)
    seen: set[Path] = set()
    output: list[Path] = []
    for document in documents:
        resolved = document.resolve()
        if resolved not in seen:
            seen.add(resolved)
            output.append(document)
    return output


def check_repository(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    readme = root / "README.md"
    if not readme.is_file():
        return ["README.md ausente"]

    readme_text = readme.read_text(encoding="utf-8")
    canonical_documents = _canonical_documents(root, readme_text)

    for document in canonical_documents:
        if not document.is_file():
            errors.append(f"Fonte canônica ausente: {document.relative_to(root)}")
            continue
        text = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK_RE.findall(text):
            target = _relative_link_target(document, raw_target, root)
            if target is not None and not target.exists():
                errors.append(
                    f"Link relativo quebrado em {document.relative_to(root)}: {raw_target}"
                )

    for match in MANUAL_METRIC_RE.finditer(readme_text):
        line = readme_text.count("\n", 0, match.start()) + 1
        errors.append(
            "README.md mantém contagem arquitetural manual "
            f"na linha {line}: {match.group(0)!r}"
        )

    workflow_dir = root / ".github" / "workflows"
    workflow_names: set[str] = set()
    if not workflow_dir.is_dir():
        errors.append("Diretório .github/workflows ausente")
    else:
        for workflow in sorted(workflow_dir.glob("*.y*ml")):
            text = workflow.read_text(encoding="utf-8")
            match = WORKFLOW_NAME_RE.search(text)
            if match:
                workflow_names.add(match.group(1).strip())

    missing_workflows = sorted(REQUIRED_WORKFLOW_NAMES - workflow_names)
    for name in missing_workflows:
        errors.append(f"Workflow obrigatório não localizado pelo nome: {name}")

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = check_repository(root)
    if errors:
        print("[docs-consistency] FALHA")
        for error in errors:
            print(f"- {error}")
        return 1
    print("[docs-consistency] OK — fontes canônicas, links e workflows consistentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
