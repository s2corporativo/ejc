"""Regressões isoladas da regra federal do PAF reconstruída sobre a main atual."""
from datetime import date

from app.services.tributario_paf import calcular_prazo_impugnacao_paf, suspenso_paf_federal


def test_suspensao_2026_nao_retroage_antes_da_vigencia() -> None:
    assert suspenso_paf_federal(date(2026, 1, 13)) is False
    assert suspenso_paf_federal(date(2026, 1, 14)) is True
    assert suspenso_paf_federal(date(2026, 1, 20)) is True
    assert suspenso_paf_federal(date(2026, 1, 21)) is False


def test_transicao_ate_31_marco_escolhe_vencimento_posterior() -> None:
    out = calcular_prazo_impugnacao_paf(date(2026, 3, 31))
    assert out["criterio"] == "transicao_adi_rfb_2_2026_maior_vencimento"
    assert out["vencimento"] == max(out["componentes"].values())


def test_apos_transicao_aplica_20_dias_uteis() -> None:
    out = calcular_prazo_impugnacao_paf(date(2026, 4, 1))
    assert out["criterio"] == "lc227_20_uteis"
    assert out["prazo"] == "20 dias úteis"
