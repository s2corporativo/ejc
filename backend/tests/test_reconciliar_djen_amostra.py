# ── tests/test_reconciliar_djen_amostra.py ───────────────────────────────────
# Issue #572 — cobre só a parte do script que não depende de banco: a
# mascaração de OAB usada no bloco de evidência minimizada. A consulta em si
# (leitura de djen_comunicacoes) é read-only e exige Postgres real; ver
# padrão de `scripts/reconciliar_status_rag.py`, também sem teste dedicado.
from scripts.reconciliar_djen_amostra import _mascarar_oab


def test_mascarar_oab_seis_digitos():
    assert _mascarar_oab("123456") == "1****6"


def test_mascarar_oab_dois_digitos_mascara_tudo():
    assert _mascarar_oab("12") == "**"


def test_mascarar_oab_um_digito_mascara_tudo():
    assert _mascarar_oab("1") == "*"


def test_mascarar_oab_vazio():
    assert _mascarar_oab("") == ""


def test_mascarar_oab_ignora_espacos_nas_pontas():
    assert _mascarar_oab(" 123456 ") == "1****6"


def test_mascarar_oab_nao_revela_digitos_centrais():
    numero = "987654"
    mascarado = _mascarar_oab(numero)
    assert numero[1:-1] not in mascarado
