from __future__ import annotations

import json
from pathlib import Path

from app.eval.curation_queue import AREAS, CENARIOS, expected_slots, load_queue, validate_queue


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "app" / "eval" / "curadoria_queue.jsonl"


def test_fila_versionada_tem_75_slots_e_matriz_completa():
    rows = load_queue(QUEUE)
    assert len(rows) == 75
    assert validate_queue(rows) == []
    assert {row["area"] for row in rows} == set(AREAS)
    assert {row["cenario"] for row in rows} == set(CENARIOS)
    assert all(row["status"] == "pendente" for row in rows)


def test_matriz_esperada_nao_atesta_caso_automaticamente():
    assert len(expected_slots()) == 75
    assert all(row["caso_id"] is None for row in expected_slots())
    assert all(row["status"] == "pendente" for row in expected_slots())


def test_fila_rejeita_slot_aprovado_sem_caso():
    rows = load_queue(QUEUE)
    rows[0] = {**rows[0], "status": "aprovado"}
    errors = validate_queue(rows)
    assert any("aprovado exige caso_id" in error for error in errors)


def test_jsonl_e_linhas_objeto():
    for line in QUEUE.read_text(encoding="utf-8").splitlines():
        payload = json.loads(line)
        assert isinstance(payload, dict)
        assert payload["slot_id"]
