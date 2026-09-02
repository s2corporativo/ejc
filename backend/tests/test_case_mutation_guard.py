"""Regressões da guarda transacional de mutações críticas do caso."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.case import CaseStatus
from app.services import case_mutation_guard as guard


class _Result:
    def scalar_one_or_none(self):
        return None


class _DB:
    def __init__(self):
        self.calls = []

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        return _Result()


def _case(status=CaseStatus.aberto):
    return SimpleNamespace(id="case-1", status=status)


async def test_serializacao_usa_lock_transacional_estavel_por_caso():
    db = _DB()

    await guard.serializar_mutacao_caso(db, "case-1")

    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert "pg_advisory_xact_lock" in sql
    assert params == {"chave": "case-mutation:case-1"}


def test_caso_terminal_recusa_mutacao_juridica():
    for status in (CaseStatus.encerrado, CaseStatus.arquivado):
        with pytest.raises(HTTPException) as exc:
            guard.garantir_caso_editavel(_case(status))
        assert exc.value.status_code == 409
        assert "reabra ou desarquive" in str(exc.value.detail).lower()


def test_caso_aberto_permanece_editavel():
    caso = _case(CaseStatus.em_producao)
    assert guard.garantir_caso_editavel(caso) is caso


def test_deadline_create_e_update_usam_guarda_compartilhada():
    from app.routers import deadlines

    fonte_criar = inspect.getsource(deadlines.criar)
    fonte_atualizar = inspect.getsource(deadlines.atualizar)
    assert "verificar_caso_editavel" in fonte_criar
    assert "verificar_caso_editavel" in fonte_atualizar
    assert "verificar_acesso_caso" not in fonte_criar
    assert "verificar_acesso_caso" not in fonte_atualizar
