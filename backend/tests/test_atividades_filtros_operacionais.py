"""Filtros aditivos da Central de Atividades sem ampliar ownership."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole
from app.routers.atividades import listar_atividades


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self):
        self.execute = AsyncMock(return_value=_Rows([]))


def _admin() -> User:
    return User(id="admin-1", role=UserRole.admin)


def _advogado() -> User:
    return User(id="adv-1", role=UserRole.advogado)


@pytest.mark.asyncio
async def test_filtros_usam_bind_params_e_nao_interpolam_identificadores():
    db = _DB()
    await listar_atividades(
        apenas_pendentes=True,
        case_id="case-1",
        client_id="client-1",
        responsavel_id="user-2",
        urgencia="critico",
        minha_fila=False,
        db=db,
        cu=_admin(),
    )

    stmt, params = db.execute.await_args.args
    sql = str(stmt)
    assert "v.case_id = :case_id" in sql
    assert "c.client_id = :client_id" in sql
    assert "v.responsavel_id = :responsavel_id" in sql
    assert "BETWEEN CURRENT_DATE AND CURRENT_DATE + 3" in sql
    assert "case-1" not in sql and "client-1" not in sql and "user-2" not in sql
    assert params == {
        "case_id": "case-1",
        "client_id": "client-1",
        "responsavel_id": "user-2",
    }


@pytest.mark.asyncio
async def test_minha_fila_prevalece_sobre_responsavel_informado():
    db = _DB()
    await listar_atividades(
        apenas_pendentes=True,
        responsavel_id="outro-user",
        minha_fila=True,
        db=db,
        cu=_admin(),
    )
    stmt, params = db.execute.await_args.args
    sql = str(stmt)
    assert "v.responsavel_id = :minha_fila_uid" in sql
    assert ":responsavel_id" not in sql
    assert params["minha_fila_uid"] == "admin-1"


@pytest.mark.asyncio
async def test_advogado_mantem_gate_de_carteira_mesmo_com_filtros():
    db = _DB()
    await listar_atividades(
        apenas_pendentes=False,
        case_id="case-alvo",
        responsavel_id="terceiro",
        db=db,
        cu=_advogado(),
    )
    stmt, params = db.execute.await_args.args
    sql = str(stmt)
    assert "cc.advogado_responsavel_id = :uid" in sql
    assert "cc.advogado_auxiliar_id = :uid" in sql
    assert params["uid"] == "adv-1"
    assert params["case_id"] == "case-alvo"
    assert params["responsavel_id"] == "terceiro"


@pytest.mark.asyncio
async def test_urgencia_invalida_falha_antes_do_banco():
    db = _DB()
    with pytest.raises(HTTPException) as excinfo:
        await listar_atividades(
            apenas_pendentes=True,
            urgencia="urgente-demais",
            db=db,
            cu=_admin(),
        )
    assert excinfo.value.status_code == 422
    db.execute.assert_not_awaited()
