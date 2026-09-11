from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.clock import FUSO_OPERACIONAL, hoje_operacional


def test_fuso_operacional_e_sao_paulo():
    assert FUSO_OPERACIONAL.key == "America/Sao_Paulo"


def test_hoje_operacional_segue_data_civil_de_sao_paulo():
    esperado = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    assert hoje_operacional() == esperado


def test_meia_noite_utc_nao_implica_novo_dia_operacional():
    instante_utc = datetime(2026, 9, 11, 0, 5, tzinfo=timezone.utc)
    assert instante_utc.astimezone(FUSO_OPERACIONAL).date().isoformat() == "2026-09-10"
