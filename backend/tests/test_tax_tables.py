"""Tabelas tributárias INSS/IRRF 2026 — base do cálculo de rescisão (Fase 5)."""

from app.services.calc.tax_tables import inss, irrf


def test_inss_faixa_a_faixa():
    # Conferido na fonte (docstring): salário R$ 5.000 → R$ 501,51
    assert inss(5000)["inss"] == 501.51


def test_inss_teto():
    # Acima do teto → desconto máximo R$ 988,09
    assert inss(10000)["inss"] == 988.09
    assert inss(20000)["inss"] == 988.09


def test_inss_primeira_faixa():
    # R$ 1.000 só na 1ª faixa (7,5%)
    assert inss(1000)["inss"] == 75.0


def test_irrf_isencao_total_lei_15270():
    # rendimento tributável (bruto - INSS) ≤ 5.000 → IRRF zerado
    r = irrf(4000, 300)
    assert r["irrf"] == 0.0


def test_irrf_redutor_parcial_sinalizado():
    # faixa 5.000,01–7.350,00 → não zera automático; sinaliza pendência
    r = irrf(6000, 600)
    assert r["redutor_parcial_pendente"] is True


def test_irrf_renda_alta_positivo():
    r = irrf(12000, 988.09)
    assert r["irrf"] > 0
    assert r["redutor_parcial_pendente"] is False
