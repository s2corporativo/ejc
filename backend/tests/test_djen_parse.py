# ── tests/test_djen_parse.py ──────────────────────────────────────────────────
# Parser tolerante da data de disponibilização do DJEN (_parse_data_disp).
# Regressão: date.fromisoformat direto abortava a captura inteira do advogado
# quando a API devolvia a data em formato não-ISO — perdendo intimações.
from datetime import date

from app.services.djen_service import _parse_data_disp


def test_iso_simples():
    assert _parse_data_disp("2026-07-05") == date(2026, 7, 5)


def test_iso_com_hora():
    assert _parse_data_disp("2026-07-05T00:00:00") == date(2026, 7, 5)


def test_formato_br_ddmmyyyy():
    assert _parse_data_disp("05/07/2026") == date(2026, 7, 5)


def test_vazio_ou_none_cai_para_hoje():
    assert _parse_data_disp("") == date.today()
    assert _parse_data_disp(None) == date.today()


def test_formato_desconhecido_nao_levanta():
    # Não pode explodir (isso abortaria o lote); cai para hoje.
    assert _parse_data_disp("julho de 2026") == date.today()
    assert _parse_data_disp("2026/07/05") == date.today()  # não-ISO, sem match BR


def test_data_invalida_no_formato_br_nao_levanta():
    assert _parse_data_disp("32/13/2026") == date.today()
