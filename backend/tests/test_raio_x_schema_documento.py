"""Contrato de documento PF/PJ na conversão da Sala."""

import pytest
from pydantic import ValidationError

from app.schemas.raio_x import ClienteConversao


def test_documento_de_14_digitos_enviado_no_campo_legado_vira_cnpj():
    cliente = ClienteConversao(
        modo="novo",
        nome="Empresa Exemplo Ltda.",
        cpf="12.345.678/0001-95",
    )
    assert cliente.cpf is None
    assert cliente.cnpj == "12345678000195"


def test_cpf_permanece_cpf_normalizado():
    cliente = ClienteConversao(
        modo="novo",
        nome="Pessoa Exemplo",
        cpf="529.982.247-25",
    )
    assert cliente.cpf == "52998224725"
    assert cliente.cnpj is None


def test_cliente_existente_exige_selecao():
    with pytest.raises(ValidationError):
        ClienteConversao(modo="existente", client_id="   ")
