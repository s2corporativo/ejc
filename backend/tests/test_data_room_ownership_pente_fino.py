"""Regressão do pente-fino de segregação do Data Room.

Cobre o vazamento residual identificado após o hardening A4:
- listagem geral sem escopo;
- criação vinculada a caso/cliente alheio;
- preservação do contrato das salas institucionais sem vínculo;
- rota legado v4 sem segregação de carteira.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.case import Case
from app.models.client import Client
from app.models.data_room import DataRoom
from app.routers.data_room import (
    DataRoomIn,
    _filtro_escopo_rooms,
    _gate_room,
    _validar_vinculos_room,
    criar_data_room,
    listar_data_rooms,
)


class _Res:
    def __init__(
        self,
        *,
        scalar_one=None,
        scalar=0,
        first=None,
        all=None,
    ):
        self._scalar_one = scalar_one
        self._scalar = scalar
        self._first = first
        self._all = [] if all is None else all

    def scalar_one_or_none(self):
        return self._scalar_one

    def scalar(self):
        return self._scalar

    def first(self):
        return self._first

    def scalars(self):
        return self

    def all(self):
        return self._all


class _DB:
    def __init__(self, results=()):
        self.results = list(results)
        self.executed = []
        self.added = []
        self.committed = False
        self.refreshed = False

    async def execute(self, stmt, *args, **kwargs):
        self.executed.append(stmt)
        if self.results:
            return self.results.pop(0)
        return _Res()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        self.refreshed = True


def _user(role: str, uid: str = "u1"):
    return SimpleNamespace(
        id=uid,
        role=SimpleNamespace(value=role),
    )


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": False}))


def test_filtro_rooms_gestao_nao_restringe():
    q = select(DataRoom)
    assert _filtro_escopo_rooms(q, _user("socio")) is q


def test_filtro_rooms_advogado_exige_ownership_nos_vinculos():
    q = _filtro_escopo_rooms(select(DataRoom), _user("advogado"))
    sql = _sql(q)
    assert "cases.id" in sql
    assert "clients.id" in sql
    assert "data_rooms.created_by =" not in sql


@pytest.mark.asyncio
async def test_listagem_aplica_escopo_antes_da_paginacao():
    db = _DB([_Res(scalar=0), _Res(all=[])])
    await listar_data_rooms(
        case_id=None,
        client_id=None,
        page=1,
        per_page=20,
        db=db,
        cu=_user("advogado"),
    )
    sql = " || ".join(_sql(stmt) for stmt in db.executed)
    assert "cases.id" in sql
    assert "clients.id" in sql
    assert "data_rooms.created_by =" not in sql


@pytest.mark.asyncio
async def test_gate_room_institucional_sem_vinculo_passa():
    """Sala sem caso/cliente permanece compartilhada para triagem institucional."""
    room = DataRoom(
        id="r1",
        case_id=None,
        client_id=None,
        created_by="outro",
    )
    assert await _gate_room(
        _DB(),
        _user("advogado", "u1"),
        room,
    ) is room


@pytest.mark.asyncio
async def test_validacao_rejeita_cliente_fora_da_carteira():
    cli = Client(id="cl1", responsavel_id="outro")
    db = _DB([_Res(scalar_one=cli), _Res(first=None)])
    with pytest.raises(HTTPException) as exc:
        await _validar_vinculos_room(
            db,
            _user("advogado", "u1"),
            case_id=None,
            client_id="cl1",
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_validacao_rejeita_cliente_incoerente_com_caso(monkeypatch):
    case = Case(id="ca1", client_id="cl-caso")
    cli = Client(id="cl-outro", responsavel_id="u1")
    db = _DB([_Res(scalar_one=case)])

    async def _acesso_ok(*args, **kwargs):
        return None

    async def _cliente_ok(*args, **kwargs):
        return cli

    monkeypatch.setattr(
        "app.routers.data_room.verificar_acesso_caso",
        _acesso_ok,
    )
    monkeypatch.setattr(
        "app.routers.data_room._cliente_visivel",
        _cliente_ok,
    )

    with pytest.raises(HTTPException) as exc:
        await _validar_vinculos_room(
            db,
            _user("advogado", "u1"),
            case_id="ca1",
            client_id="cl-outro",
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_criacao_canonica_valida_vinculos_antes_de_gravar(monkeypatch):
    chamado = False

    async def _validar(*args, **kwargs):
        nonlocal chamado
        chamado = True
        return None, None

    monkeypatch.setattr(
        "app.routers.data_room._validar_vinculos_room",
        _validar,
    )
    db = _DB()
    out = await criar_data_room(
        DataRoomIn(nome="Sala segura"),
        db,
        _user("advogado", "u1"),
    )
    assert chamado is True
    assert db.committed is True
    assert db.refreshed is True
    assert out["created_by"] == "u1"


