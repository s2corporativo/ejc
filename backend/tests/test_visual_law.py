"""Testes do cálculo puro de breakeven de acordo (POST /visual-law/breakeven).

O endpoint em si é coberto pelo contrato frontend↔backend
(tests/test_api_contract.py); aqui validamos a matemática determinística
e o shape esperado por frontend/src/types/visualLaw.ts.
"""
import pytest

from app.routers.visual_law import (
    BreakevenRequest,
    MARGEM_NEGOCIACAO,
    calcular_breakeven,
)


def _base(**overrides):
    params = dict(
        valor_causa=100_000.0,
        prob_exito=0.6,
        tempo_anos=2.0,
        tribunal="TJMG",
        selic_anual=0.10,
        selic_fonte="fallback",
        custas_pct=5.0,
        honorarios_sucumbencia_pct=10.0,
    )
    params.update(overrides)
    return calcular_breakeven(**params)


def test_formula_breakeven_valores_conhecidos():
    r = _base()
    # valor_esperado = 100000 × 0.6 = 60000
    assert r.valor_esperado == 60_000.0
    # custos = 100000×5% + 100000×10%×(1−0.6) = 5000 + 4000 = 9000
    assert r.custos_estimados == 9_000.0
    # líquido nominal = 51000; VPL = 51000 / 1.1² = 42148.76
    assert r.vpl_litigio == pytest.approx(51_000.0 / 1.21, abs=0.01)
    assert r.breakeven == r.vpl_litigio
    assert r.sugestao_acordo == pytest.approx(
        r.breakeven * (1 + MARGEM_NEGOCIACAO), abs=0.01
    )
    # comparativo coerente: custo do tempo = nominal − VPL
    assert r.comparativo.litigio_vpl == r.vpl_litigio
    assert r.comparativo.acordo_imediato_equivalente == r.breakeven
    assert r.comparativo.custo_do_tempo == pytest.approx(
        51_000.0 - r.vpl_litigio, abs=0.01
    )
    assert len(r.memoria_calculo) >= 8


def test_liquido_negativo_nao_gera_breakeven_negativo():
    # prob baixa: 100000×0.05 = 5000 esperado; custos = 5000 + 9500 = 14500 → líquido −9500
    r = _base(prob_exito=0.05)
    assert r.vpl_litigio < 0
    assert r.breakeven == 0.0
    assert r.sugestao_acordo == 0.0


def test_selic_maior_reduz_vpl():
    baixa = _base(selic_anual=0.05)
    alta = _base(selic_anual=0.15)
    assert alta.vpl_litigio < baixa.vpl_litigio


def test_shape_do_response_bate_com_frontend():
    r = _base().model_dump()
    assert set(r) == {
        "parametros", "valor_esperado", "custos_estimados", "vpl_litigio",
        "sugestao_acordo", "breakeven", "comparativo", "memoria_calculo",
    }
    assert set(r["parametros"]) == {
        "valor_causa", "prob_exito", "tempo_anos", "tribunal",
        "selic_anual", "selic_fonte", "custas_pct", "honorarios_sucumbencia_pct",
    }
    assert set(r["comparativo"]) == {
        "litigio_vpl", "acordo_imediato_equivalente", "custo_do_tempo",
    }
    assert all(isinstance(p, str) for p in r["memoria_calculo"])


def test_request_valida_limites():
    with pytest.raises(ValueError):
        BreakevenRequest(valor_causa=0, prob_exito=0.5)
    with pytest.raises(ValueError):
        BreakevenRequest(valor_causa=1000, prob_exito=1.5)
    # payload real do frontend (CalculadoraAcordo.tsx) é aceito
    req = BreakevenRequest(
        valor_causa=150_000,
        prob_exito=0.6,
        tribunal="TJMG",
        tempo_anos=3,
        custas_pct=4.5,
        honorarios_sucumbencia_pct=10,
        case_id="abc-123",
    )
    assert req.case_id == "abc-123"  # aceito e ignorado no cálculo
