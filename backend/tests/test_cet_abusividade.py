"""Vertical bancário determinístico — CET (Resolução CMN nº 4.881/2020 e
IN BCB nº 83/2021) e motor de abusividade de juros
(REsp 1.061.530/RS, Tema 27/STJ).

Cobertura:
  • CET de caso conferível à mão (1 parcela em 365 dias → taxa exata);
  • CET 12x conhecido (TIR ~2,92% a.m.) + resíduo do fluxo ≈ 0;
  • tarifas/IOF elevam o CET;
  • divergência CET informado × calculado (> 0,5 p.p.);
  • abusividade 2x a média → indício forte + expurgo Price correto (BCB mockado);
  • 1,3x → zona de atenção; BCB fora → fail-soft (nunca inventa média);
  • Decimal em todo o cálculo (sem float drift).
"""
from datetime import date
from decimal import Decimal

import pytest

from app.services import abusividade_service as ab
from app.services.calc.cet import calcular_cet, parcela_price, add_months
from app.routers import analise_bancaria


# ══════════════════════════════════════════════════════════════════════════
# CET — casos conferíveis à mão
# ══════════════════════════════════════════════════════════════════════════
def test_cet_uma_parcela_365_dias_exato():
    # 10.000 liberado; 11.000 devolvidos exatamente 365 dias depois:
    # 10000 = 11000/(1+CET)^(365/365) → CET anual = 10% exato.
    r = calcular_cet(
        valor_liberado=10_000,
        data_liberacao=date(2026, 1, 10),
        parcelas=[{"valor": 11_000, "vencimento": date(2027, 1, 10)}],
    )
    assert r["cet_anual_pct"] == pytest.approx(10.0, abs=1e-6)
    # mensal = (1,1)^(1/12) − 1 ≈ 0,7974%
    assert r["cet_mensal_pct"] == pytest.approx(0.7974, abs=1e-3)
    assert r["valor_liberado_liquido"] == 10_000.0
    assert r["memoria_calculo"] and r["convergencia"]["iteracoes"] >= 1
    assert any("4.881/2020" in b for b in r["base_legal"])
    assert any("83/2021" in b for b in r["base_legal"])
    assert not any("3.517/2007" in b for b in r["base_legal"])


def test_cet_12x_1000_sobre_10000():
    # TIR mensal clássica: 10000 = 1000·a(12; i) → i ≈ 2,9226% a.m.
    # (com meses-calendário reais a variação fica em centésimos de p.p.)
    r = calcular_cet(
        valor_liberado=10_000,
        data_liberacao=date(2026, 1, 10),
        n_parcelas=12, valor_parcela=1_000,
        primeiro_vencimento=date(2026, 2, 10),
    )
    assert r["cet_mensal_pct"] == pytest.approx(2.9226, abs=0.1)
    assert r["cet_anual_pct"] == pytest.approx(41.3, abs=1.5)
    assert len(r["fluxo"]) == 12
    assert r["total_pago"] == 12_000.0
    # resíduo do fluxo: PV das parcelas à taxa achada ≈ valor líquido
    assert abs(r["convergencia"]["residuo"]) < 0.01


def test_cet_tarifas_e_iof_elevam_o_resultado():
    base = dict(valor_liberado=10_000, data_liberacao=date(2026, 1, 10),
                n_parcelas=12, valor_parcela=1_000,
                primeiro_vencimento=date(2026, 2, 10))
    sem = calcular_cet(**base)
    com = calcular_cet(**base, tarifas_incluidas=350, iof=120)
    assert com["valor_liberado_liquido"] == 9_530.0
    assert com["cet_anual_pct"] > sem["cet_anual_pct"]
    assert com["cet_mensal_pct"] > sem["cet_mensal_pct"]


def test_cet_divergencia_detectada_acima_de_meio_pp():
    kw = dict(valor_liberado=10_000, data_liberacao=date(2026, 1, 10),
              parcelas=[{"valor": 11_000, "vencimento": date(2027, 1, 10)}])
    # calculado = 10,0% a.a.; informado 8,0% → diferença 2,0 p.p. > 0,5
    r = calcular_cet(**kw, cet_informado_aa_pct=8.0)
    d = r["divergencia"]
    assert d is not None
    assert d["achado"] == "CET informado diverge do calculado"
    assert d["diferenca_pp"] == pytest.approx(2.0, abs=1e-4)
    assert any("CDC" in b for b in d["base_legal"])
    assert any("4.881/2020" in b for b in d["base_legal"])
    # dentro do limiar (0,3 p.p.) → sem achado
    assert calcular_cet(**kw, cet_informado_aa_pct=10.3)["divergencia"] is None


def test_cet_validacoes():
    with pytest.raises(ValueError):   # nenhum modo de fluxo
        calcular_cet(valor_liberado=1000, data_liberacao=date(2026, 1, 1))
    with pytest.raises(ValueError):   # líquido ≤ 0
        calcular_cet(valor_liberado=100, data_liberacao=date(2026, 1, 1),
                     tarifas_incluidas=200,
                     parcelas=[{"valor": 50, "vencimento": date(2026, 2, 1)}])
    with pytest.raises(ValueError):   # vencimento antes da liberação
        calcular_cet(valor_liberado=1000, data_liberacao=date(2026, 3, 1),
                     parcelas=[{"valor": 500, "vencimento": date(2026, 2, 1)}])


def test_decimal_sem_float_drift():
    # Price em Decimal puro, aceita entradas string
    p = parcela_price("10000", "0.08", 12)
    assert isinstance(p, Decimal)
    assert p == Decimal("1326.95")           # 10000·0,08/(1−1,08⁻¹²)
    assert parcela_price(Decimal("12000"), Decimal("0"), 12) == Decimal("1000.00")
    # add_months faz clamp no fim do mês
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


async def test_endpoint_cet_shape():
    req = analise_bancaria.CETIn(
        valor_liberado=10_000, data_liberacao=date(2026, 1, 10),
        n_parcelas=12, valor_parcela=1_000, primeiro_vencimento=date(2026, 2, 10),
        tarifas_incluidas=350, iof=120, cet_informado_aa_pct=20.0,
    )
    r = await analise_bancaria.calcular_cet_endpoint(req, cu=None)
    for k in ("cet_mensal_pct", "cet_anual_pct", "memoria_calculo", "divergencia",
              "base_legal", "fluxo", "convergencia", "avisos"):
        assert k in r
    assert any("4.881/2020" in b for b in r["base_legal"])
    with pytest.raises(Exception):  # pydantic: nenhum modo de fluxo informado
        analise_bancaria.CETIn(valor_liberado=10_000, data_liberacao=date(2026, 1, 10))


# ══════════════════════════════════════════════════════════════════════════
# Abusividade — BCB/Olinda mockado
# ══════════════════════════════════════════════════════════════════════════
def _mock_olinda(monkeypatch, taxas_am=(3.0, 4.0, 5.0), periodo="2024-03-01"):
    chamadas = []

    async def fake(params: dict) -> list:
        chamadas.append(params)
        if params.get("$select") == "InicioPeriodo":
            return [{"InicioPeriodo": periodo}]
        return [{"Modalidade": "Crédito pessoal não-consignado - Pré-fixado",
                 "Segmento": "PESSOA FÍSICA",
                 "TaxaJurosAoMes": t, "TaxaJurosAoAno": t * 14} for t in taxas_am]

    monkeypatch.setattr(ab, "olinda_get", fake)
    return chamadas


async def test_abusividade_2x_indicio_forte_com_expurgo(monkeypatch):
    chamadas = _mock_olinda(monkeypatch)  # média a.m. = 4,0
    r = await ab.avaliar_abusividade(
        taxa_contrato_am_pct=8.0, modalidade="credito_pessoal",
        data_contrato=date(2024, 3, 10),
        valor_financiado=10_000, n_parcelas=12,
    )
    assert r["taxa_media"]["ao_mes"]["media"] == 4.0
    assert r["razao"] == pytest.approx(2.0)
    assert r["veredito"] == "indicio_forte_abusividade"
    assert "1.061.530" in r["fundamentacao"]
    assert any("1.061.530" in b for b in r["base_legal"])
    assert any("judicial" in a.lower() or "HITL" in a for a in r["avisos"])
    # a consulta histórica usou a data do contrato
    assert any("le '2024-03-10'" in (c.get("$filter") or "") for c in chamadas)
    # expurgo Price conferível à mão (Decimal):
    e = r["expurgo"]
    assert e["parcela_original"] == pytest.approx(1326.95, abs=0.01)
    assert e["parcela_revisada"] == pytest.approx(1065.52, abs=0.01)
    assert e["economia_mensal"] == pytest.approx(1326.95 - 1065.52, abs=0.02)
    assert e["economia_total"] == pytest.approx(12 * (1326.95 - 1065.52), abs=0.25)
    assert e["memoria"]


async def test_abusividade_1_3x_zona_de_atencao(monkeypatch):
    _mock_olinda(monkeypatch)  # média 4,0 → 5,2/4,0 = 1,3x
    r = await ab.avaliar_abusividade(taxa_contrato_am_pct=5.2,
                                     modalidade="credito_pessoal")
    assert r["veredito"] == "zona_de_atencao"
    assert r["razao"] == pytest.approx(1.3)
    assert r["expurgo"] is None


async def test_abusividade_abaixo_de_1_2x_normal(monkeypatch):
    _mock_olinda(monkeypatch)
    r = await ab.avaliar_abusividade(taxa_contrato_am_pct=4.4,
                                     modalidade="credito_pessoal")
    assert r["veredito"] == "dentro_da_normalidade"


async def test_abusividade_bcb_fora_fail_soft(monkeypatch):
    async def caiu(params):
        raise ab.TaxaMediaIndisponivel("timeout BCB")

    monkeypatch.setattr(ab, "olinda_get", caiu)
    r = await ab.avaliar_abusividade(taxa_contrato_am_pct=8.0,
                                     modalidade="credito_pessoal")
    assert r["veredito"] == "indeterminado"
    assert r["taxa_media"] is None and r["razao"] is None and r["expurgo"] is None
    assert any("BCB" in a for a in r["avisos"])
    # fail-soft preserva os dados do contrato p/ nova tentativa
    assert r["taxa_contrato_am_pct"] == 8.0


async def test_abusividade_modalidade_sem_dados(monkeypatch):
    _mock_olinda(monkeypatch)
    r = await ab.avaliar_abusividade(taxa_contrato_am_pct=8.0,
                                     modalidade="modalidade_que_nao_existe")
    assert r["veredito"] == "indeterminado"
    assert r["taxa_media"] is None


async def test_endpoint_abusividade_shape(monkeypatch):
    _mock_olinda(monkeypatch)
    req = analise_bancaria.AbusividadeIn(
        taxa_contrato_am_pct=8.0, modalidade="credito_pessoal",
        data_contrato=date(2024, 3, 10), valor_financiado=10_000, n_parcelas=12,
    )
    r = await analise_bancaria.avaliar_abusividade_endpoint(req, cu=None)
    for k in ("taxa_contrato_am_pct", "taxa_media", "razao", "veredito",
              "fundamentacao", "expurgo", "base_legal", "avisos"):
        assert k in r
    assert r["expurgo"]["economia_total"] > 0


# ══════════════════════════════════════════════════════════════════════════
# Integração com a esteira de peças (minuta revisional)
# ══════════════════════════════════════════════════════════════════════════
async def test_formatar_expurgo_para_peca(monkeypatch):
    _mock_olinda(monkeypatch)
    r = await ab.avaliar_abusividade(
        taxa_contrato_am_pct=8.0, modalidade="credito_pessoal",
        valor_financiado=10_000, n_parcelas=12,
    )
    txt = ab.formatar_expurgo_para_peca(r)
    assert txt and "1.061.530" in txt and "1.326,95" in txt and "1.065,52" in txt
    # sem expurgo (ou payload arbitrário) → None, nada entra no prompt
    assert ab.formatar_expurgo_para_peca({"expurgo": None}) is None
    assert ab.formatar_expurgo_para_peca({"expurgo": {"parcela_original": "x"}}) is None
    assert ab.formatar_expurgo_para_peca("injecao") is None


async def test_contexto_revisional_recebe_expurgo(monkeypatch):
    from app.routers.bank_analysis import _montar_contexto_revisional
    _mock_olinda(monkeypatch)
    aval = await ab.avaliar_abusividade(
        taxa_contrato_am_pct=8.0, modalidade="credito_pessoal",
        valor_financiado=10_000, n_parcelas=12,
    )
    txt = ab.formatar_expurgo_para_peca(aval)
    analise = {"banco": "Banco X", "periodo_inicio": "2024-01-01",
               "periodo_fim": "2024-06-30", "total_abusivo": 500.0}
    cobr = [{"titulo": "Tarifa indevida", "descricao": "TAC", "prioridade": "alta",
             "base_legal": "CDC 51", "valor": 500.0}]
    fatos, pedidos = _montar_contexto_revisional(analise, cobr, txt)
    assert "CÁLCULO DETERMINÍSTICO" in fatos and "1.326,95" in fatos
    assert "taxa média de mercado" in pedidos and "e)" in pedidos
    # sem expurgo → contexto original inalterado (sem item e)
    fatos2, pedidos2 = _montar_contexto_revisional(analise, cobr)
    assert "CÁLCULO DETERMINÍSTICO" not in fatos2 and "e)" not in pedidos2
