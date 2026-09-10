"""Regressões P0 do contrato DataJud → prazos.

A sincronização DataJud pode atualizar movimentações, mas não materializa prazo
processual até existir candidato + motor canônico + HITL auditável.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.case import Case
from app.routers import datajud as router_datajud


class _Resultado:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DB:
    def __init__(self, value):
        self._value = value
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, _query):
        return _Resultado(self._value)


@pytest.mark.asyncio
async def test_sync_case_nao_dispara_pipeline_de_prazo(monkeypatch):
    case = Case(id="case-1", numero_processo="0000000-00.2026.8.13.0000")
    db = _DB(case)

    acesso = AsyncMock(return_value=case)
    sync_movimentos = AsyncMock(return_value={"novos": 2})
    sync_prazos = AsyncMock(side_effect=AssertionError("pipeline de prazo não pode ser chamado"))
    monkeypatch.setattr(router_datajud, "verificar_acesso_caso", acesso)
    monkeypatch.setattr(router_datajud.datajud_service, "sincronizar_caso", sync_movimentos)
    monkeypatch.setattr(router_datajud.datajud_service, "sincronizar_prazos_datajud", sync_prazos)

    resposta = await router_datajud.sync_case("case-1", db=db, current_user=object())

    assert resposta["synced"] == {"novos": 2}
    assert resposta["prazos"]["bloqueado"] is True
    assert resposta["prazos"]["criados"] == 0
    assert resposta["prazos"]["motivo"] == "prazo_datajud_requer_motor_canonico_e_hitl"
    sync_prazos.assert_not_awaited()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_prazos_preserva_ownership_e_falha_com_409(monkeypatch):
    case = Case(id="case-1", numero_processo="0000000-00.2026.8.13.0000")
    db = _DB(case)

    acesso = AsyncMock(return_value=case)
    sync_prazos = AsyncMock(side_effect=AssertionError("pipeline legado não pode ser chamado"))
    monkeypatch.setattr(router_datajud, "verificar_acesso_caso", acesso)
    monkeypatch.setattr(router_datajud.datajud_service, "sincronizar_prazos_datajud", sync_prazos)

    with pytest.raises(HTTPException) as excinfo:
        await router_datajud.sync_prazos("case-1", db=db, current_user=object())

    assert excinfo.value.status_code == 409
    assert "motor canônico" in excinfo.value.detail
    acesso.assert_awaited_once_with(db, pytest.ANY, "case-1")
    sync_prazos.assert_not_awaited()
