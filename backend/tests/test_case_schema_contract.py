from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.case import CaseCreate, CaseUpdate


def _payload(**overrides):
    data = {
        "titulo": "Caso de teste",
        "area": "civil",
        "client_id": "00000000-0000-0000-0000-000000000001",
    }
    data.update(overrides)
    return data


def test_case_type_create_e_update_rejeitam_valor_fora_do_contrato():
    with pytest.raises(ValidationError):
        CaseCreate(**_payload(case_type="qualquer-coisa"))
    with pytest.raises(ValidationError):
        CaseUpdate(case_type="qualquer-coisa")


def test_case_type_normaliza_caixa_e_espacos():
    caso = CaseCreate(**_payload(case_type="  EXTRAJUDICIAL "))
    assert caso.case_type == "extrajudicial"


def test_titulo_e_ids_respeitam_largura_do_modelo():
    with pytest.raises(ValidationError):
        CaseCreate(**_payload(titulo="x" * 256))
    with pytest.raises(ValidationError):
        CaseCreate(**_payload(client_id="x" * 37))
    with pytest.raises(ValidationError):
        CaseUpdate(advogado_responsavel_id="x" * 37)


def test_varchars_de_casos_falham_antes_do_banco_quando_excedem_coluna():
    with pytest.raises(ValidationError):
        CaseUpdate(tribunal="T" * 21)
    with pytest.raises(ValidationError):
        CaseUpdate(comarca="C" * 101)
    with pytest.raises(ValidationError):
        CaseUpdate(vara="V" * 101)
    with pytest.raises(ValidationError):
        CaseUpdate(parte_contraria="P" * 256)
    with pytest.raises(ValidationError):
        CaseUpdate(risco="R" * 21)
    with pytest.raises(ValidationError):
        CaseUpdate(extrajudicial_type="E" * 51)
    with pytest.raises(ValidationError):
        CaseUpdate(kanban_column="K" * 101)
