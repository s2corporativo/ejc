#!/usr/bin/env python3
"""Fila de curadoria do gold set jurídico real do EJC.

Este módulo controla os slots necessários para atingir a cobertura mínima do
projeto, mas não cria fatos, teses ou atesta casos. A fila é metadado de
execução; somente JSONL com casos reais e aprovado por ``gold_governance`` conta
como gold jurídico.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

AREAS = ("consumidor", "trabalhista", "civel", "penal", "tributario")
CENARIOS = ("normal", "fronteira", "excecao")
SLOTS_POR_AREA_CENARIO = 5
QUEUE_NAME = "curadoria_queue.jsonl"


def expected_slots() -> list[dict[str, object]]:
    slots: list[dict[str, object]] = []
    for area in AREAS:
        for cenario in CENARIOS:
            for n in range(1, SLOTS_POR_AREA_CENARIO + 1):
                slots.append(
                    {
                        "slot_id": f"{area[:3].upper()}-{cenario[:3].upper()}-{n:03d}",
                        "area": area,
                        "cenario": cenario,
                        "status": "pendente",
                        "responsavel": None,
                        "caso_id": None,
                        "observacao": None,
                    }
                )
    return slots


def load_queue(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no}: cada linha deve ser objeto")
        rows.append(value)
    return rows


def validate_queue(rows: list[dict[str, object]]) -> list[str]:
    errors: list[str] = []
    expected = {str(row["slot_id"]): row for row in expected_slots()}
    actual = {str(row.get("slot_id")): row for row in rows}
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing:
        errors.append(f"slots ausentes: {', '.join(missing)}")
    if extra:
        errors.append(f"slots desconhecidos: {', '.join(extra)}")
    if len(actual) != len(rows):
        errors.append("slot_id duplicado")
    valid_statuses = {"pendente", "em_curadoria", "em_revisao", "aprovado", "bloqueado"}
    for slot_id, row in actual.items():
        if slot_id not in expected:
            continue
        if row.get("area") != expected[slot_id]["area"]:
            errors.append(f"{slot_id}: area divergente")
        if row.get("cenario") != expected[slot_id]["cenario"]:
            errors.append(f"{slot_id}: cenario divergente")
        if row.get("status") not in valid_statuses:
            errors.append(f"{slot_id}: status inválido")
        if row.get("status") == "aprovado" and not row.get("caso_id"):
            errors.append(f"{slot_id}: aprovado exige caso_id")
    return errors


def summary(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "total_slots": len(rows),
        "por_status": dict(sorted(Counter(str(r.get("status")) for r in rows).items())),
        "por_area": {
            area: dict(
                sorted(
                    Counter(
                        str(r.get("status"))
                        for r in rows
                        if r.get("area") == area
                    ).items()
                )
            )
            for area in AREAS
        },
        "por_cenario": {
            cenario: sum(1 for r in rows if r.get("cenario") == cenario)
            for cenario in CENARIOS
        },
    }


def write_initial(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) for row in expected_slots()
    ) + "\n"
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fila de curadoria do gold set EJC")
    parser.add_argument("--queue", type=Path, default=Path(__file__).with_name(QUEUE_NAME))
    parser.add_argument("command", choices=("init", "check", "summary"))
    args = parser.parse_args()

    if args.command == "init":
        if args.queue.exists():
            raise SystemExit(f"fila já existe: {args.queue}; não sobrescrevendo")
        write_initial(args.queue)
        print(f"fila criada: {args.queue} ({len(expected_slots())} slots)")
        return 0

    if not args.queue.exists():
        print(f"fila ausente: {args.queue}")
        return 2
    rows = load_queue(args.queue)
    errors = validate_queue(rows)
    if args.command == "check":
        if errors:
            for error in errors:
                print(f"ERRO: {error}")
            return 1
        print(f"OK: fila válida com {len(rows)} slots; nenhum slot é atestado por este comando")
        return 0

    print(json.dumps(summary(rows), ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
