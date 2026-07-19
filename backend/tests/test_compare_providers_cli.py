from __future__ import annotations


def test_carregar_gold_exige_id_e_query(tmp_path):
    from app.eval.compare_providers import carregar_gold

    arquivo = tmp_path / "gold.jsonl"
    arquivo.write_text('{"id":"x"}\n', encoding="utf-8")
    try:
        carregar_gold(str(arquivo))
    except ValueError as exc:
        assert "id e query" in str(exc)
    else:
        raise AssertionError("gold inválido deveria falhar")
