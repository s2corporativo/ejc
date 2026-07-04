"""Calculadora de acordo (POST /visual-law/breakeven) — matemática e fallback.

Contrato do frontend: frontend/src/types/visualLaw.ts (BreakevenRequest/Response).
"""
from math import pow as _pow

import pytest

from app.routers import visual_law as vl
from app.routers.visual_law import BreakevenRequest, breakeven


class _User:
    id = "u1"
    role = type("R", (), {"value": "advogado"})()


async def _chamar(monkeypatch, **kw):
    # Sem BCB nos testes: força o fallback determinístico.
    async def _sem_bcb():
        return None

    monkeypatch.setattr(vl, "_selic_anual_bcb", _sem_bcb)
    return await breakeven(BreakevenRequest(**kw), db=None, cu=_User())


async def test_breakeven_matematica_basica(monkeypatch):
    r = await _chamar(
        monkeypatch,
        valor_causa=100_000.0,
        prob_exito=0.8,
        tempo_anos=2.0,
        selic_anual=0.10,
        custas_pct=2.0,
        honorarios_sucumbencia_pct=10.0,
    )
    esperado = 100_000.0 * 0.8                        # 80_000
    custos = 100_000.0 * 0.02 + 100_000.0 * 0.10 * 0.2  # 2_000 + 2_000
    vpl = (esperado - custos) / _pow(1.10, 2.0)
    assert r["valor_esperado"] == 80_000.0
    assert r["custos_estimados"] == 4_000.0
    assert r["vpl_litigio"] == round(vpl, 2)
    assert r["breakeven"] == r["vpl_litigio"] == r["sugestao_acordo"]
    assert r["comparativo"]["custo_do_tempo"] == round(esperado - custos - vpl, 2)
    # Selic informada pelo usuário → fonte própria (não "fallback" de referência).
    assert r["parametros"]["selic_fonte"] == "usuario"
    assert any("VPL" in m for m in r["memoria_calculo"])


async def test_breakeven_defaults_documentados(monkeypatch):
    r = await _chamar(monkeypatch, valor_causa=50_000.0, prob_exito=0.5)
    p = r["parametros"]
    assert p["tempo_anos"] == vl.TEMPO_ANOS_PADRAO
    assert p["selic_anual"] == vl.SELIC_ANUAL_FALLBACK
    assert p["selic_fonte"] == "fallback"
    # Premissas assumidas aparecem na memória de cálculo (nada silencioso).
    memoria = " ".join(r["memoria_calculo"])
    assert "estimativa padrão" in memoria
    assert "BCB indisponível" in memoria


async def test_breakeven_selic_bcb_quando_disponivel(monkeypatch):
    async def _bcb():
        return 0.12

    monkeypatch.setattr(vl, "_selic_anual_bcb", _bcb)
    r = await breakeven(
        BreakevenRequest(valor_causa=10_000.0, prob_exito=1.0, tempo_anos=1.0),
        db=None,
        cu=_User(),
    )
    assert r["parametros"]["selic_anual"] == 0.12
    assert r["parametros"]["selic_fonte"] == "bcb"
    assert r["vpl_litigio"] == round(10_000.0 / 1.12, 2)


async def test_breakeven_valida_entrada():
    with pytest.raises(Exception):
        BreakevenRequest(valor_causa=0, prob_exito=0.5)   # gt=0
    with pytest.raises(Exception):
        BreakevenRequest(valor_causa=1000, prob_exito=1.5)  # le=1
