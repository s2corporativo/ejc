from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.main import app
from app.schemas.process import ProcessCreate, ProcessUpdate
from app.services.processo_service import _legacy_text


def test_process_schema_accepts_administrative_identifier():
    payload = ProcessCreate(numero_cnj="SEI-12345/2026", tipo="administrativo")
    assert payload.numero_cnj == "SEI-12345/2026"


@pytest.mark.parametrize(
    "tipo",
    [
        "judicial",
        "recurso",
        "cautelar",
        "execucao",
        "administrativo",
        "extrajudicial",
        "arbitral",
        "outro",
    ],
)
def test_process_schema_preserves_existing_operational_types(tipo: str):
    assert ProcessCreate(tipo=tipo).tipo == tipo


def test_process_schema_rejects_invalid_cnj_check_digit():
    with pytest.raises(ValidationError):
        ProcessCreate(numero_cnj="0000000-00.0000.0.00.0000")


def test_process_update_preserves_unset_fields():
    payload = ProcessUpdate(status="suspenso")
    assert payload.model_dump(exclude_unset=True) == {"status": "suspenso"}


def test_legacy_adapter_only_truncates_the_compatibility_copy():
    original = "TRIBUNAL-CANONICO-COM-NOME-COMPLETO"
    assert _legacy_text(original, 20) == original[:20]
    assert original == "TRIBUNAL-CANONICO-COM-NOME-COMPLETO"
    assert _legacy_text(None, 20) is None


def test_router_does_not_embed_sql_rules():
    source = (
        Path(__file__).parents[1] / "app/routers/processes.py"
    ).read_text(encoding="utf-8")
    assert "sqlalchemy import text" not in source
    assert "INSERT INTO processes" not in source

    # Valida o contrato HTTP efetivamente montado na aplicação, sem acoplar o
    # teste à divisão interna entre router e casos_router.
    efetivas = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("GET", "/api/cases/{case_id}/processes") in efetivas
    assert ("PATCH", "/api/processes/{pid}") in efetivas
    assert ("POST", "/api/processes/{pid}/principal") in efetivas
    assert ("POST", "/api/processes/{pid}/arquivar") in efetivas
    assert ("POST", "/api/processes/{pid}/desarquivar") in efetivas
    assert ("DELETE", "/api/processes/{pid}") in efetivas


def test_service_preserves_legacy_accessors_and_write_through():
    source = (
        Path(__file__).parents[1] / "app/services/processo_service.py"
    ).read_text(encoding="utf-8")
    assert "async def processo_principal" in source
    assert "async def numero_processo_efetivo" in source
    assert "async def obter_processo" in source
    assert "_sync_case_legacy" in source
    assert "_clear_case_legacy" in source
    assert "_legacy_text(process.tribunal, 20)" in source
    assert "Use a ação específica de arquivamento" in source
    assert "informe is_principal=false" in source


def test_repository_is_the_only_process_persistence_layer_in_wave2():
    repository = (
        Path(__file__).parents[1] / "app/repositories/process_repository.py"
    ).read_text(encoding="utf-8")
    assert "class ProcessRepository" in repository
    assert "async def list_for_case" in repository
    assert "async def principal" in repository
    assert "async def clear_principal" in repository
    assert "async def lock_case" in repository
    assert ".with_for_update()" in repository


def test_all_mutations_use_the_same_case_lock():
    source = (
        Path(__file__).parents[1] / "app/services/processo_service.py"
    ).read_text(encoding="utf-8")
    assert source.count("await process_repository.lock_case") == 6
