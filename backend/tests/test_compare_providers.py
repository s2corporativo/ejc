from __future__ import annotations

import pytest

from app.eval.compare_providers import ResultadoProvider, agregar, carregar_gold


def test_fallback_nao_conta_como_execucao_valida():
    resumo = agregar([
        ResultadoProvider(
            caso_id="a", provider_pedido="maritaca", provider_real="groq",
            fallback=True, citacoes_total=2, citacoes_nao_confirmadas=2,
            custo_brl=1.0, duracao_ms=500,
        ),
        ResultadoProvider(
            caso_id="b", provider_pedido="maritaca", provider_real="maritaca",
            citacoes_total=4, citacoes_nao_confirmadas=1,
            groundedness=0.8, custo_brl=0.2, duracao_ms=100,
        ),
    ])["maritaca"]
    assert resumo["n_validos"] == 1
    assert resumo["fallbacks_excluidos"] == 1
    assert resumo["taxa_citacoes_nao_confirmadas"] == 0.25
    assert resumo["groundedness_media"] == 0.8
    assert resumo["custo_total_brl"] == 0.2
    assert resumo["duracao_media_ms"] == 100


def test_erros_ficam_separados():
    resumo = agregar([
        ResultadoProvider(caso_id="a", provider_pedido="anthropic", erro="indisponível")
    ])["anthropic"]
    assert resumo["n_validos"] == 0
    assert resumo["erros"] == 1


def test_gold_exige_id_e_query(tmp_path):
    arquivo = tmp_path / "gold.jsonl"
    arquivo.write_text('{"id":"x"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="id e query"):
        carregar_gold(str(arquivo))
