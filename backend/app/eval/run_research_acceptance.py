#!/usr/bin/env python3
"""Valida a régua sintética de pesquisa sem fingir uma execução contra o RAG.

A execução online é feita no ambiente de produção. Este comando garante que a
régua tem 20 perguntas, áreas cobertas, fontes do catálogo e critérios de
segurança suficientes para a homologação.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = Path(__file__).with_name("research_acceptance.synthetic.jsonl")
CATALOG = Path(__file__).with_name("fontes_publicas_iniciais.json")


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    known = {str(item["id"]) for item in catalog["fontes"]}
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    errors: list[str] = []
    areas = {str(c.get("area")) for c in cases}
    if len(cases) != 20:
        errors.append(f"esperados 20 casos sintéticos, encontrados {len(cases)}")
    if areas != {"consumidor_bancario", "trabalhista_empresarial", "civel", "processual_civil", "penal", "tributario"}:
        errors.append(f"cobertura de áreas inválida: {sorted(areas)}")
    ids: set[str] = set()
    for case in cases:
        cid = str(case.get("id") or "")
        if not cid or cid in ids:
            errors.append(f"id ausente ou duplicado: {cid}")
        ids.add(cid)
        if len(str(case.get("pergunta") or "")) < 20:
            errors.append(f"pergunta curta: {cid}")
        missing = [source for source in case.get("fontes_esperadas", []) if source not in known]
        if missing:
            errors.append(f"{cid}: fontes fora do catálogo: {missing}")
        required = {str(x).lower() for x in case.get("deve_exigir", [])}
        if len(required) < 2:
            errors.append(f"{cid}: precisa de ao menos dois critérios de segurança")
    if errors:
        print("RESEARCH ACCEPTANCE: ERRO")
        print("\n".join(f"- {e}" for e in errors))
        return 2
    print("RESEARCH ACCEPTANCE: OK")
    print(f"casos={len(cases)} areas={len(areas)} fontes_catalogadas={len(known)}")
    print("Observação: este smoke é offline; não mede recall nem substitui a execução no RAG de produção.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
