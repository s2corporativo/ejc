"""Motor de prescrição/decadência — cálculos jurídicos sensíveis (laudo Fase 5)."""
from datetime import date

import pytest

from app.services.calc.prescricao import calcular, EntradaPrescricao


def _calc(chave, termo, hoje):
    return calcular(EntradaPrescricao(chave=chave, termo_inicial=termo), hoje=hoje)


def test_civel_geral_10_anos():
    r = _calc("civel_geral", date(2020, 1, 1), date(2025, 1, 1))
    assert r["data_limite"] == "2030-01-01"
    assert r["duracao"] == "10 ano(s)"
    assert r["tipo"] == "prescricao"
    assert r["situacao"] == "em_curso"


def test_reparacao_civil_3_anos_consumada():
    r = _calc("reparacao_civil", date(2020, 1, 1), date(2025, 1, 1))
    assert r["data_limite"] == "2023-01-01"
    assert r["situacao"] == "consumada"
    assert r["dias_restantes"] < 0


def test_cdc_vicio_duravel_90_dias_decadencia():
    r = _calc("cdc_vicio_duravel", date(2025, 1, 1), date(2025, 1, 10))
    assert r["tipo"] == "decadencia"
    assert r["duracao"] == "90 dia(s)"
    assert r["data_limite"] == "2025-04-01"


def test_alerta_prazo_proximo():
    # 10 dias antes do limite → alerta de prazo se encerrando
    r = _calc("seguro", date(2024, 1, 1), date(2024, 12, 25))  # seguro = 1 ano
    assert r["situacao"] == "em_curso"
    assert "ATENÇÃO" in r["alerta"]


def test_chave_desconhecida():
    with pytest.raises(ValueError):
        _calc("inexistente", date(2020, 1, 1), date(2025, 1, 1))
