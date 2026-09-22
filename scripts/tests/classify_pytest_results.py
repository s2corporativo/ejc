#!/usr/bin/env python3
"""Classifica resultados pytest/JUnit e falha fechado em skips DB obrigatórios."""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

INFRA_RE = re.compile(
    r"socket\.gaierror|name or service not known|temporary failure in name resolution|"
    r"connection refused|could not connect|connection is closed|cannot connect|"
    r"no such host|server closed the connection unexpectedly|"
    r"operationalerror.*(postgres|asyncpg|database|connection)",
    re.IGNORECASE,
)
ENDPOINT_RE = re.compile(
    r"(^|[_./-])(api|endpoint|route|router|health|smoke|http)([_./-]|$)|"
    r"status[_ ]?code|http[s]?\s*\d{3}",
    re.IGNORECASE,
)
DB_SKIP_RE = re.compile(
    r"RUN_DB_TESTS|SCHEMA_CHECK_DATABASE_URL|requer\s+Postgres|"
    r"Postgres(?:SQL)?[^\n]{0,80}(?:migration|pgvector|banco|database)|"
    r"banco\s+(?:real|inacess[ií]vel)|pgvector",
    re.IGNORECASE,
)


def _text(node: ET.Element) -> str:
    values = [*node.attrib.values(), *node.itertext()]
    return " ".join(part.strip() for part in values if part and part.strip())


def classify(path: Path) -> dict[str, object]:
    root = ET.parse(path).getroot()
    counts = {"infra_error": 0, "test_failure": 0, "endpoint_failure": 0, "skip": 0}
    cases: list[dict[str, str]] = []
    blocking_db_skips: list[dict[str, str]] = []

    for case in root.iter("testcase"):
        name = f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}"
        skipped = case.find("skipped")
        failure = case.find("failure")
        error = case.find("error")

        if skipped is not None:
            category = "skip"
            detail = _text(skipped)
            if DB_SKIP_RE.search(f"{name} {detail}"):
                blocking_db_skips.append({"test": name, "detail": detail[:1200]})
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

    return {
        "source": str(path),
        "counts": counts,
        "blocking_db_skip_count": len(blocking_db_skips),
        "blocking_db_skips": blocking_db_skips,
        "cases": cases,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on-db-skip", action="store_true")
    parser.add_argument("junit_xml", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = classify(args.junit_xml)
    except (OSError, ET.ParseError) as exc:
        print(
            json.dumps(
                {"error": type(exc).__name__, "detail": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.fail_on_db_skip and report["blocking_db_skip_count"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
