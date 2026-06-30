"""Verbas rescisórias (CLT) — cálculos sensíveis (laudo Fase 5).

Testa invariantes e regras estruturais (sem fixar valores que dependem das
tabelas tributárias INSS/IRRF), para travar a lógica contra regressão.
"""
from datetime import date

import pytest

from app.services.calc.trabalhista import calcular, EntradaRescisao, _anos_completos


def _ent(**kw):
    base = dict(salario=3000.0, admissao=date(2014, 1, 10), demissao=date(2024, 6, 20))
    base.update(kw)
    return EntradaRescisao(**base)


def test_tipo_invalido():
    with pytest.raises(ValueError):
        calcular(_ent(tipo="xpto"))


def test_salario_nao_positivo():
    with pytest.raises(ValueError):
        calcular(_ent(salario=0))


def test_demissao_antes_da_admissao():
    with pytest.raises(ValueError):
        calcular(_ent(admissao=date(2024, 1, 1), demissao=date(2023, 1, 1)))


def test_anos_completos():
    assert _anos_completos(date(2014, 1, 10), date(2024, 6, 20)) == 10
    assert _anos_completos(date(2014, 6, 20), date(2024, 6, 19)) == 9  # 1 dia antes do aniversário


def test_aviso_proporcional_e_cap_90():
    # 10 anos completos → 30 + 3*10 = 60 dias
    r10 = calcular(_ent(tipo="sem_justa_causa"))
    assert r10["parametros"]["aviso_dias"] == 60
    # 30+ anos → teto de 90 dias
    r30 = calcular(_ent(admissao=date(1990, 1, 10), demissao=date(2024, 6, 20),
                        tipo="sem_justa_causa"))
    assert r30["parametros"]["aviso_dias"] == 90


def test_pedido_demissao_sem_aviso_nem_fgts():
    r = calcular(_ent(tipo="pedido_demissao", saldo_fgts=10000.0))
    assert r["saque_fgts_liberado"] is False
    assert r["parametros"]["aviso_dias"] == 0
    assert not any("Aviso prévio" in p["verba"] for p in r["proventos"])
    assert not any("Multa FGTS" in p["verba"] for p in r["proventos"])


def test_sem_justa_causa_tem_multa_fgts_40():
    r = calcular(_ent(tipo="sem_justa_causa", saldo_fgts=10000.0))
    assert r["saque_fgts_liberado"] is True
    multa = next((p for p in r["proventos"] if "Multa FGTS" in p["verba"]), None)
    assert multa is not None and "40%" in multa["verba"]
    assert multa["valor"] == pytest.approx(4000.0, abs=0.01)  # 40% de 10.000


def test_liquido_consistente():
    r = calcular(_ent(tipo="sem_justa_causa", saldo_fgts=5000.0))
    assert r["total_proventos"] > 0
    assert r["liquido"] == pytest.approx(r["total_proventos"] - r["total_descontos"], abs=0.02)
