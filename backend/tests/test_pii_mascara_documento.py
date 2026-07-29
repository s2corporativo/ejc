"""Máscara canônica de CPF/CNPJ (services/pii_crypto.mascarar_documento).

É a única forma pela qual documento de cliente sai nas respostas que cruzam a
base inteira ignorando a segregação de carteira — busca global e checagem de
conflito de interesses (EOAB arts. 34-35). Por isso o que se testa aqui não é
"formata bonito", e sim QUANTO vaza: quais dígitos ficam visíveis, e que
entrada esquisita não vira vazamento por acidente.

Sem banco e sem chave de PII — função pura.
"""
from __future__ import annotations

import pytest

from app.services.pii_crypto import mascarar_documento


# ── CPF: miolo visível, extremos ocultos ─────────────────────────────────────

def test_cpf_expoe_apenas_o_miolo():
    assert mascarar_documento("111.444.777-35") == "***.444.777-**"


def test_cpf_sem_formatacao_da_o_mesmo_resultado():
    """A entrada chega dos dois jeitos (clients.cpf é normalizado; case_partes
    .cpf_cnpj é texto livre). A máscara não pode depender disso."""
    assert mascarar_documento("11144477735") == mascarar_documento("111.444.777-35")


def test_cpf_nao_revela_os_tres_primeiros_nem_os_verificadores():
    """Os 3 primeiros + os 2 dígitos verificadores são justamente o que
    permitiria reconstruir/confirmar o CPF por força bruta a partir do miolo."""
    mascarado = mascarar_documento("11144477735")
    assert "111" not in mascarado
    assert not mascarado.endswith("35")


# ── CNPJ: idem, sem expor a raiz ─────────────────────────────────────────────

def test_cnpj_oculta_a_raiz_a_ordem_e_o_verificador():
    assert mascarar_documento("12.345.678/0001-95") == "**.345.678/****-**"


def test_cnpj_nao_vaza_ordem_nem_verificador():
    mascarado = mascarar_documento("12345678000195")
    assert "0001" not in mascarado
    assert "95" not in mascarado


# ── Entradas que não são documento ───────────────────────────────────────────

@pytest.mark.parametrize("entrada", [None, "", "   ", "sem digitos", "---"])
def test_sem_digitos_devolve_none(entrada):
    assert mascarar_documento(entrada) is None


@pytest.mark.parametrize("entrada", ["123", "1234567", "111444777356789"])
def test_comprimento_inesperado_devolve_none_em_vez_de_parcial(entrada):
    """Dado sujo (digitação errada, RG no campo de CPF) não pode virar máscara
    "melhor esforço": não se sabe quais posições são seguras de mostrar, então
    a resposta correta é não mostrar nada."""
    assert mascarar_documento(entrada) is None


def test_nenhum_digito_da_entrada_sobrevive_em_bloco():
    """Trava a propriedade que interessa: a saída nunca contém o documento
    inteiro, qualquer que seja a formatação da entrada."""
    for doc in ("11144477735", "12345678000195"):
        assert doc not in (mascarar_documento(doc) or "")
