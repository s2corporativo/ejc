"""Contrato do UUID no endpoint de detalhe do caso."""

from __future__ import annotations

from typing import get_type_hints

import pytest
from pydantic import TypeAdapter, ValidationError

from app.routers.cases import CaseIdPath, detalhe


def test_case_id_path_aceita_uuid_e_preserva_string():
    case_id = "08a9e898-9868-4515-8a34-132ad291cd44"

    validado = TypeAdapter(CaseIdPath).validate_python(case_id)

    assert validado == case_id
    assert isinstance(validado, str)


@pytest.mark.parametrize(
    "case_id",
    [
        "nao-e-uuid",
        "08a9e898-9868-4515-8a34-132ad291cd4",
        "08a9e898-9868-4515-8a34-132ad291cd4g",
    ],
)
def test_case_id_path_rejeita_formato_malformado(case_id: str):
    with pytest.raises(ValidationError):
        TypeAdapter(CaseIdPath).validate_python(case_id)


def test_detalhe_declara_o_contrato_validado_no_path():
    hints = get_type_hints(detalhe, include_extras=True)

    assert hints["case_id"] == CaseIdPath
