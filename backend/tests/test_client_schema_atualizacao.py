"""Regressão dos achados 7 e 12 da auditoria do módulo Clientes.

  • Achado 7: ClientUpdate descartava data_nascimento/profissao/nome_fantasia/
    complemento/origem em silêncio (ausentes do schema) — agora aceitos.
  • Achado 12: `email` aceitava qualquer string — agora valida formato
    (EmailStr) e tolera "" como ausência de valor, mesmo padrão de
    data_nascimento.

Puramente Pydantic — sem banco.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate


def test_client_update_aceita_campos_antes_descartados():
    payload = ClientUpdate(
        data_nascimento="1990-05-20",
        profissao="Engenheira",
        nome_fantasia="Fantasia LTDA",
        complemento="Sala 12",
        origem="site",
    )
    assert payload.data_nascimento.isoformat() == "1990-05-20"
    assert payload.profissao == "Engenheira"
    assert payload.nome_fantasia == "Fantasia LTDA"
    assert payload.complemento == "Sala 12"
    assert payload.origem == "site"


def test_client_update_origem_invalida_rejeitada():
    with pytest.raises(ValidationError):
        ClientUpdate(origem="origem-que-nao-existe")


def test_client_update_data_nascimento_vazia_vira_none():
    payload = ClientUpdate(data_nascimento="")
    assert payload.data_nascimento is None


@pytest.mark.parametrize("schema_cls", [ClientCreate, ClientUpdate])
def test_email_formato_invalido_rejeitado(schema_cls):
    kwargs = {"nome": "Fulano"} if schema_cls is ClientCreate else {}
    with pytest.raises(ValidationError):
        schema_cls(email="nao-e-email", **kwargs)


@pytest.mark.parametrize("schema_cls", [ClientCreate, ClientUpdate])
def test_email_vazio_vira_none(schema_cls):
    kwargs = {"nome": "Fulano"} if schema_cls is ClientCreate else {}
    payload = schema_cls(email="  ", **kwargs)
    assert payload.email is None


@pytest.mark.parametrize("schema_cls", [ClientCreate, ClientUpdate])
def test_email_normaliza_para_minusculo(schema_cls):
    kwargs = {"nome": "Fulano"} if schema_cls is ClientCreate else {}
    payload = schema_cls(email="Fulano@Exemplo.COM", **kwargs)
    assert payload.email == "fulano@exemplo.com"


def test_client_response_nao_quebra_leitura_de_email_legado_invalido():
    """A validação estrita do achado 12 é só de ESCRITA (ClientCreate/
    ClientUpdate). ClientResponse serializa dado JÁ GRAVADO — um cliente
    cadastrado antes desta auditoria pode ter e-mail malformado no banco;
    validar formato também na LEITURA faria uma única linha ruim derrubar a
    listagem inteira (a mesma classe de 500 do achado crítico 1, agora via
    e-mail em vez de cpf/cnpj). ClientResponse precisa tolerar isso."""
    payload = ClientResponse.model_validate({
        "id": "cli-1", "status": "ativo", "created_at": "2026-01-01T00:00:00Z",
        "email": "isto-nao-e-um-email-valido",
    })
    assert payload.email == "isto-nao-e-um-email-valido"
