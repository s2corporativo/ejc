"""Hardening do HTML bancário: dados de localização não podem virar markup."""
from app.services.bank_report import gerar_documento


def test_cidade_e_escapada_antes_de_interpolar_no_html():
    payload = "<img src=x onerror=alert(1)>"
    html = gerar_documento(
        "notificacao",
        {"cliente_nome": "Cliente", "banco": "Banco", "total_abusivo": 0},
        [],
        {"cidade": payload, "advogado_nome": "Advogado", "advogado_oab": "OAB/MG 1"},
    )
    assert payload not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
