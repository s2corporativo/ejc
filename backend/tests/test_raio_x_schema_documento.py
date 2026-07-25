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


# ── P0-473: DV obrigatório + rejeição de truncamento silencioso ───────────────

def test_cpf_com_dv_invalido_e_rejeitado():
    with pytest.raises(ValidationError, match="dígito verificador"):
        ClienteConversao(modo="novo", nome="Pessoa", cpf="529.982.247-26")


def test_cnpj_com_dv_invalido_e_rejeitado():
    with pytest.raises(ValidationError, match="dígito verificador"):
        ClienteConversao(modo="novo", nome="Empresa", cnpj="12.345.678/0001-96")


def test_cnpj_valido_com_mascara_normaliza():
    cliente = ClienteConversao(
        modo="novo", nome="Empresa", cnpj="12.345.678/0001-95"
    )
    assert cliente.cnpj == "12345678000195"


def test_comprimento_invalido_nao_trunca_e_rejeita():
    # 16 dígitos no campo legado: antes truncava para 14; agora é erro explícito.
    with pytest.raises(ValidationError, match="14 dígitos"):
        ClienteConversao(modo="novo", nome="Empresa", cpf="1234567890123456")


def test_cpf_curto_e_rejeitado():
    with pytest.raises(ValidationError, match="11 dígitos"):
        ClienteConversao(modo="novo", nome="Pessoa", cpf="123.456.789")


def test_documento_vazio_segue_opcional():
    cliente = ClienteConversao(modo="novo", nome="Só Nome", cpf="", cnpj="")
    assert cliente.cpf is None
    assert cliente.cnpj is None
