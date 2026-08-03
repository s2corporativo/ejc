"""Validação de formato de UUID em path param (Issue #581).

Função pura — sem banco. O teste de integração (formato válido mas caso
inexistente → 404; formato inválido → 422, antes de tocar o banco) vive em
test_caso_detalhe_uuid_dblevel.py, porque depende de uma sessão real e do
handler completo.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.id_validation import validar_uuid_path


@pytest.mark.parametrize(
    "malformado",
    ["abc", "123", "", "  ", "' OR 1=1--", "<script>", "12345678-1234-1234-1234"],
)
def test_formato_invalido_levanta_422(malformado):
    with pytest.raises(HTTPException) as exc:
        validar_uuid_path(malformado)
    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    "valido",
    [
        "550e8400-e29b-41d4-a716-446655440000",
        "550E8400-E29B-41D4-A716-446655440000",  # maiúsculas também são UUID
    ],
)
def test_formato_valido_devolve_a_propria_string(valido):
    """A assinatura da rota mantém `case_id: str` — o validador não pode
    converter para `uuid.UUID`, que mudaria o valor que chega ao handler."""
    resultado = validar_uuid_path(valido)
    assert resultado == valido
    assert isinstance(resultado, str)


def test_mensagem_de_erro_usa_o_rotulo_informado():
    """Rota com mais de um path param de identificador precisa que o erro
    aponte qual campo — "id inválido" genérico não ajuda a depurar."""
    with pytest.raises(HTTPException) as exc:
        validar_uuid_path("abc", rotulo="ID do documento")
    assert "ID do documento" in exc.value.detail
