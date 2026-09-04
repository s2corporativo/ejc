from __future__ import annotations

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


def _caso(status=CaseStatus.aberto):
    return SimpleNamespace(id="case-1", status=status)


async def test_serializacao_usa_lock_transacional_estavel_por_caso():
    db = _DB()
    await guard.serializar_mutacao_caso(db, "case-1")
    sql, params = db.calls[0]
    assert "pg_advisory_xact_lock" in sql
    assert params == {"chave": "case-mutation:case-1"}


def test_caso_terminal_recusa_mutacao_juridica():
    for status in (CaseStatus.encerrado, CaseStatus.arquivado):
        with pytest.raises(HTTPException) as exc:
            guard.garantir_caso_editavel(_caso(status))
        assert exc.value.status_code == 409


def test_caso_aberto_permanece_editavel():
    caso = _caso(CaseStatus.em_producao)
    assert guard.garantir_caso_editavel(caso) is caso
