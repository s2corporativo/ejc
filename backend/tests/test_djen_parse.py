# ── tests/test_djen_parse.py ──────────────────────────────────────────────────
# Parser tolerante da data de disponibilização do DJEN (_parse_data_disp).
# Regressão P0: data ausente/inválida não pode virar date.today(), porque isso
# fabrica um marco temporal que não veio da fonte e pode contaminar prazo.
from datetime import date

from app.services.djen_service import _parse_data_disp


def test_iso_simples():
    assert _parse_data_disp("2026-07-05") == date(2026, 7, 5)


def test_iso_com_hora():
    assert _parse_data_disp("2026-07-05T00:00:00") == date(2026, 7, 5)


def test_formato_br_ddmmyyyy():
    assert _parse_data_disp("05/07/2026") == date(2026, 7, 5)


def test_vazio_ou_none_permanece_sem_data():
    assert _parse_data_disp("") is None
    assert _parse_data_disp(None) is None


def test_formato_desconhecido_nao_levanta_nem_inventa_data():
    assert _parse_data_disp("julho de 2026") is None
    assert _parse_data_disp("2026/07/05") is None


def test_data_invalida_no_formato_br_nao_levanta_nem_inventa_data():
    assert _parse_data_disp("32/13/2026") is None
