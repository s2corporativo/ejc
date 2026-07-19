"""Regressões da auditoria de QA (bugs de backend).

Item 1: POST /clients com data_nascimento string crua estourava 500
        (asyncpg DataError: 'str' object has no attribute 'toordinal') porque o
        schema tipava data_nascimento como str e a coluna é DATE. Agora o schema
        valida como date ANTES do INSERT → 422 (ValidationError) para inválido,
        e "" / None viram ausência de data.

Item 2: POST /cases com `area` fora do enum casearea estourava 500
        (InvalidTextRepresentationError). Agora o schema valida contra CaseArea
        → 422 (ValidationError).

Testes de nível de schema (Pydantic v2): a ValidationError é o que o FastAPI
converte em HTTP 422 — não depende de banco nem de auth.
"""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.client import ClientCreate
from app.schemas.case import CaseCreate
from app.models.case import CaseArea


# ── Item 1: data_nascimento ───────────────────────────────────────────────────

def test_client_data_nascimento_iso_valida_vira_date():
    c = ClientCreate(tipo="PF", nome="Fulano", data_nascimento="1990-05-20")
    assert c.data_nascimento == date(1990, 5, 20)


@pytest.mark.parametrize("vazio", ["", "   ", None])
def test_client_data_nascimento_vazia_ou_none_vira_none(vazio):
    c = ClientCreate(tipo="PF", nome="Fulano", data_nascimento=vazio)
    assert c.data_nascimento is None


def test_client_data_nascimento_omitida_vira_none():
    c = ClientCreate(tipo="PF", nome="Fulano")
    assert c.data_nascimento is None


@pytest.mark.parametrize("ruim", ["not-a-date", "2020-13-40", "20/05/1990-xx"])
def test_client_data_nascimento_invalida_dispara_422(ruim):
    # Antes: string crua chegava na coluna DATE → 500. Agora: 422 no schema.
    with pytest.raises(ValidationError):
        ClientCreate(tipo="PF", nome="Fulano", data_nascimento=ruim)


# ── Item 2: area do caso ──────────────────────────────────────────────────────

def test_case_area_valida_ok():
    c = CaseCreate(titulo="Caso", area="civil", client_id="cli-1")
    assert c.area == "civil"


def test_case_todas_areas_do_enum_sao_aceitas():
    for a in CaseArea:
        c = CaseCreate(titulo="Caso", area=a.value, client_id="cli-1")
        assert c.area == a.value


@pytest.mark.parametrize("ruim", ["zzz", "", "civel", "CIVIL", "trabalhistaX"])
def test_case_area_invalida_dispara_422(ruim):
    # Antes: enum casearea desconhecido → InvalidTextRepresentationError (500).
    with pytest.raises(ValidationError):
        CaseCreate(titulo="Caso", area=ruim, client_id="cli-1")
