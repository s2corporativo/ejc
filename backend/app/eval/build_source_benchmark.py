#!/usr/bin/env python3
"""Gera benchmark de recuperação a partir da Biblioteca Jurídica versionada.

O resultado mede se o RAG encontra fichas que já existem no acervo. Não é gold
set de casos: não inventa fatos, não atesta tese e não substitui curadoria
humana. Cada item preserva a proveniência declarada no front matter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIBRARY = ROOT / "docs" / "biblioteca_juridica"
DEFAULT_OUT = ROOT / "backend" / "app" / "eval" / "benchmarks" / "rag_source_curated.jsonl"
OFFICIAL_SUFFIXES = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br")


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    data: dict[str, str] = {}
    for line in text[4:end].splitlines():
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line.strip())
        if match:
            data[match.group(1)] = match.group(2).strip().strip('"')
    return data


def first_heading(text: str) -> str:
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            body = text[end + len("\n---"):]
    for line in body.splitlines():
        raw = line.strip()
        if re.match(r"^#{1,6}\s+\S", raw):
            return re.sub(r"^#{1,6}\s+", "", raw)[:240]
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith(("---", ">", "#")):
            return line[:240]
    return ""


def official_urls(text: str, meta: dict[str, str]) -> list[str]:
    values = re.findall(r"https://[^\s)>'\"]+", text)
    values += re.findall(r"https://[^\s,]+", meta.get("link_official", ""))
    urls: list[str] = []
    for url in values:
        url = url.rstrip(".,;:)")
        host = re.sub(r"^https://", "", url).split("/", 1)[0].lower().rstrip(".")
        if host.endswith(OFFICIAL_SUFFIXES) and url not in urls:
            urls.append(url)
    return urls


def area(meta: dict[str, str], path: Path) -> str:
    value = meta.get("area_juridica", "").strip().lower()
    if value:
        return value.replace(" ", "_")
    return path.parent.name.lower()


def make_case(path: Path) -> dict[str, object] | None:
    text = path.read_text(encoding="utf-8")
    meta = frontmatter(text)
    # O benchmark de proveniência não deve transformar material gerado por IA
    # ou ficha sem data de verificação em evidência jurídica. Esses documentos
    # permanecem disponíveis no RAG conforme sua própria política, mas ficam
    # fora desta régua.
    if meta.get("gerado_por_IA", "").strip().lower() != "false":
        return None
    if not meta.get("last_verified_at", "").strip():
        return None
    urls = official_urls(text, meta)
    if not urls:
        return None
    title = first_heading(text) or path.stem.replace("-", " ")
    canonical = meta.get("canonical_id") or f"LIB-{hashlib.sha256(str(path).encode()).hexdigest()[:12]}"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    query = re.sub(r"^BIBLIOTECA JUR[IÍ]DICA EJC\s*[—-]\s*", "", title, flags=re.I)
    query = "Recuperar a fonte jurídica da Biblioteca EJC sobre " + query.rstrip(".")
    return {
        "id": f"SRC-{canonical}",
        "status": "fonte_curada",
        "material_type": "biblioteca_juridica_versionada",
        "ficticio": True,
        "atestado_por": None,
        "area": area(meta, path),
        "cenario": "fonte",
        "query": query,
        "expected_titulos": [title],
        "expected_categorias": [meta.get("tipo_camada", "conhecimento_juridico")],
        "expected_sources": urls,
        "proveniencia": {
            "arquivo": str(path.relative_to(ROOT)),
            "canonical_id": canonical,
            "nivel_confianca": meta.get("nivel_confianca"),
            "gerado_por_IA": meta.get("gerado_por_IA"),
            "last_verified_at": meta.get("last_verified_at"),
            "sha256_snapshot_local": digest,
        },
        "nota": "Benchmark de recuperação por proveniência; não é caso real nem atestação jurídica humana.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    rows = [make_case(path) for path in sorted(LIBRARY.rglob("*.md"))]
    rows = [row for row in rows if row is not None]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(f"benchmark fonte-curada: {len(rows)} itens -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
