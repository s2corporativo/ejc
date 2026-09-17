import json
import sys

import pytest

from app.eval.legal_bench import load_cases
from scripts import legal_bench as cli


def test_load_cases_rejeita_id_duplicado(tmp_path):
    path = tmp_path / "cases.jsonl"
    row = {
        "id": "case-1",
        "area": "civil",
        "prompt": "Caso sintético",
        "source_scoring_enabled": False,
    }
    path.write_text(
        json.dumps(row) + "\n" + json.dumps(row) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="id de caso duplicado"):
        load_cases(path)


def test_load_answers_rejeita_id_duplicado(tmp_path):
    path = tmp_path / "answers.jsonl"
    row = {"id": "case-1", "issue_keys": []}
    path.write_text(
        json.dumps(row) + "\n" + json.dumps(row) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="id de resposta duplicado"):
        cli._load_answers(path)


def test_cli_nao_sobrescreve_arquivo_de_entrada(tmp_path, monkeypatch):
    cases = tmp_path / "cases.jsonl"
    answers = tmp_path / "answers.jsonl"
    cases.write_text(
        json.dumps(
            {
                "id": "case-1",
                "area": "civil",
                "prompt": "Caso sintético",
                "requires_adverse_research": False,
                "source_scoring_enabled": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    answers.write_text(
        json.dumps(
            {
                "id": "case-1",
                "issue_keys": [],
                "fact_ids": [],
                "research_records": [],
                "conclusion_status": "sem_conclusao_segura",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    original = cases.read_text(encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "legal_bench",
            "--cases",
            str(cases),
            "--answers",
            str(answers),
            "--out",
            str(cases),
        ],
    )
    with pytest.raises(SystemExit, match="não pode sobrescrever"):
        cli.main()
    assert cases.read_text(encoding="utf-8") == original
