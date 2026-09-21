#!/usr/bin/env python3
"""Classifica resultados pytest/JUnit para separar infraestrutura de regressões.

O CI deve imprimir este relatório antes de devolver o código de saída original do
pytest. Falhas de DNS/conexão do banco não podem ser confundidas com falhas de
assertion ou de endpoint.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

INFRA_RE = re.compile(
    r"socket\.gaierror|name or service not known|connection refused|"
    r"could not connect|connection is closed|cannot connect|"
    r"no such host|operationalerror.*(postgres|asyncpg|database|connection)",
    re.IGNORECASE,
)
ENDPOINT_RE = re.compile(
    r"(^|[_./-])(api|endpoint|route|router|health|smoke|http)([_./-]|$)|"
    r"status[_ ]?code|http[s]?\s*\d{3}",
    re.IGNORECASE,
)


def _text(node: ET.Element) -> str:
    values = [*node.attrib.values(), *node.itertext()]
    return " ".join(part.strip() for part in values if part and part.strip())


def classify(path: Path) -> dict[str, object]:
    root = ET.parse(path).getroot()
    counts = {"infra_error": 0, "test_failure": 0, "endpoint_failure": 0, "skip": 0}
    cases: list[dict[str, str]] = []
    for case in root.iter("testcase"):
        name = f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}"
        skipped = case.find("skipped")
        failure = case.find("failure")
        error = case.find("error")
        if skipped is not None:
            category = "skip"
            detail = _text(skipped)
        elif failure is not None or error is not None:
            node = failure if failure is not None else error
            detail = _text(node) if node is not None else ""
            if INFRA_RE.search(detail):
                category = "infra_error"
            elif ENDPOINT_RE.search(name) or ENDPOINT_RE.search(detail):
                category = "endpoint_failure"
            else:
                category = "test_failure"
        else:
            continue
        counts[category] += 1
        cases.append({"category": category, "test": name, "detail": detail[:1200]})

    return {"source": str(path), "counts": counts, "cases": cases}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} JUNIT_XML", file=sys.stderr)
        return 2
    path = Path(argv[1])
    report = classify(path)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
