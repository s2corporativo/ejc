"""Visual Law — POST /visual-law/breakeven (calculadora de acordo).

Cobre:
  1. Cálculo puro (calcular_breakeven): valores conhecidos, defaults por
     tribunal, clamp do breakeven em 0, memória de cálculo.
  2. Contrato HTTP: shape exato do BreakevenResponse do frontend
     (types/visualLaw.ts), auth JWT obrigatória, validação Pydantic.
Determinístico: a Selic é sempre injetada/mockada (sem rede).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.calc.breakeven_acordo import (
    SELIC_ANUAL_FALLBACK,
    TEMPO_MEDIO_ANOS,
    TEMPO_PADRAO_ANOS,
    calcular_breakeven,
)


# ── 1. Cálculo puro ───────────────────────────────────────────────────────────

def test_calculo_valores_conhecidos():
    r = calcular_breakeven(
        valor_causa=100_000, prob_exito=0.6, tempo_anos=2,
        custas_pct=2.0, honorarios_sucumbencia_pct=10.0,
        selic_anual=0.10, selic_fonte="fallback",
    )
    assert r["valor_esperado"] == 60_000.0
    # custas 2% (2000) + sucumbência esperada 0.4 × 10% × 100k (4000)
    assert r["custos_estimados"] == 6_000.0
    # (60000 − 6000) / 1.1² = 54000 / 1.21
    assert r["vpl_litigio"] == pytest.approx(44_628.10, abs=0.01)
    assert r["breakeven"] == r["vpl_litigio"] == r["sugestao_acordo"]
    assert r["comparativo"]["litigio_vpl"] == r["vpl_litigio"]
    assert r["comparativo"]["acordo_imediato_equivalente"] == r["breakeven"]
    assert r["comparativo"]["custo_do_tempo"] == pytest.approx(
        54_000.0 - 44_628.10, abs=0.01)
    assert len(r["memoria_calculo"]) >= 6


def test_defaults_por_tribunal_e_padrao():
    r = calcular_breakeven(valor_causa=50_000, prob_exito=0.5, tribunal="tjmg")
    assert r["parametros"]["tempo_anos"] == TEMPO_MEDIO_ANOS["TJMG"]
    assert r["parametros"]["tribunal"] == "TJMG"
    assert r["parametros"]["custas_pct"] == 2.0
    assert r["parametros"]["honorarios_sucumbencia_pct"] == 10.0
    assert r["parametros"]["selic_anual"] == SELIC_ANUAL_FALLBACK
    r2 = calcular_breakeven(valor_causa=50_000, prob_exito=0.5, tribunal="outro")
    assert r2["parametros"]["tempo_anos"] == TEMPO_PADRAO_ANOS


def test_resultado_negativo_clampa_breakeven_em_zero():
    r = calcular_breakeven(
        valor_causa=100_000, prob_exito=0.0, tempo_anos=3,
        custas_pct=2.0, honorarios_sucumbencia_pct=10.0, selic_anual=0.10,
    )
    assert r["vpl_litigio"] < 0            # só custos, nenhum ganho esperado
    assert r["breakeven"] == 0.0
    assert r["sugestao_acordo"] == 0.0


# ── 2. Contrato HTTP ──────────────────────────────────────────────────────────

URL = "/api/visual-law/breakeven"


class _AdvFake:
    id = "adv-1"
    role = "advogado"


@pytest.fixture()
def http_ctx(monkeypatch):
    from app.main import app
    from app.core.security import get_current_user, create_access_token
    import app.routers.visual_law as vl

    async def _selic_fake(fallback=0.15):
        return 0.12, "bcb"

    monkeypatch.setattr(vl.bcb_service, "selic_anual_atual", _selic_fake)
    app.dependency_overrides[get_current_user] = lambda: _AdvFake()
    token = create_access_token("adv-1", "advogado")
    client = TestClient(app)
    try:
        yield client, {"Authorization": f"Bearer {token}"}
    finally:
        app.dependency_overrides.clear()


def test_breakeven_exige_jwt():
    from app.main import app
    r = TestClient(app).post(URL, json={"valor_causa": 1000, "prob_exito": 0.5})
    assert r.status_code == 401


def test_breakeven_contrato_completo(http_ctx):
    client, auth = http_ctx
    r = client.post(URL, headers=auth, json={
        "valor_causa": 150_000, "prob_exito": 0.6, "tribunal": "TJMG",
        "custas_pct": 2, "honorarios_sucumbencia_pct": 10, "case_id": "c-1",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # shape exato do BreakevenResponse (frontend/src/types/visualLaw.ts)
    assert set(body) == {"parametros", "valor_esperado", "custos_estimados",
                         "vpl_litigio", "sugestao_acordo", "breakeven",
                         "comparativo", "memoria_calculo"}
    assert set(body["parametros"]) == {
        "valor_causa", "prob_exito", "tempo_anos", "tribunal", "selic_anual",
        "selic_fonte", "custas_pct", "honorarios_sucumbencia_pct"}
    assert set(body["comparativo"]) == {
        "litigio_vpl", "acordo_imediato_equivalente", "custo_do_tempo"}
    assert body["parametros"]["selic_fonte"] == "bcb"
    assert body["parametros"]["selic_anual"] == 0.12
    assert body["parametros"]["tempo_anos"] == TEMPO_MEDIO_ANOS["TJMG"]
    assert isinstance(body["memoria_calculo"], list) and body["memoria_calculo"]


def test_breakeven_selic_informada_e_fonte_fallback(http_ctx):
    client, auth = http_ctx
    r = client.post(URL, headers=auth, json={
        "valor_causa": 10_000, "prob_exito": 0.5, "selic_anual": 0.08,
    })
    assert r.status_code == 200
    assert r.json()["parametros"]["selic_anual"] == 0.08
    assert r.json()["parametros"]["selic_fonte"] == "fallback"


def test_breakeven_validacao_pydantic(http_ctx):
    client, auth = http_ctx
    for body in (
        {"valor_causa": 0, "prob_exito": 0.5},       # valor_causa > 0
        {"valor_causa": 1000, "prob_exito": 1.5},    # prob_exito ≤ 1
        {"valor_causa": 1000, "prob_exito": 0.5, "tempo_anos": -1},
        {"valor_causa": 1000, "prob_exito": 0.5, "custas_pct": 101},
    ):
        r = client.post(URL, headers=auth, json=body)
        assert r.status_code == 422, body
