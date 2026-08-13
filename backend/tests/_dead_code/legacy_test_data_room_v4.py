"""Contratos do router LEGADO data_room_v4 (movido a _dead_code em
12/08/2026 — docs/consolidacao/MAPA_VERDADE_V1.md). Estes testes protegem o
comportamento de depreciação do contrato antigo (header deprecation,
rejeição de sala avulsa para não-gestores, validação de carteira) contra o
código arquivado — não contra main.py. NÃO reativar sem decisão escrita.
"""
from __future__ import annotations
from types import SimpleNamespace
import pytest
from fastapi import HTTPException, Response
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
from app.routers._dead_code.data_room_v4 import (
    SalaCreate,
    _validar_cliente_v4,
    criar_sala,
    listar_salas,
)
@pytest.mark.asyncio
async def test_v4_listagem_advogado_filtra_clientes_visiveis():
    db = _DB([_Res(all=[])])
    response = Response()
    await listar_salas(
        response=response,
        db=db,
        cu=_user("advogado", "u1"),
    )
    sql = _sql(db.executed[0])
    assert "client_id IS NOT NULL" in sql
    assert "clients.id" in sql
    assert response.headers["deprecation"] == "true"


@pytest.mark.asyncio
async def test_v4_rejeita_sala_avulsa_para_nao_gestao():
    with pytest.raises(HTTPException) as exc:
        await _validar_cliente_v4(
            _DB(),
            _user("advogado", "u1"),
            None,
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_v4_criacao_chama_validacao_de_carteira(monkeypatch):
    chamado = False

    async def _validar(*args, **kwargs):
        nonlocal chamado
        chamado = True

    monkeypatch.setattr(
        "app.routers._dead_code.data_room_v4._validar_cliente_v4",
        _validar,
    )
    db = _DB()
    response = Response()
    await criar_sala(
        SalaCreate(nome="Sala legado", client_id="cl1"),
        response=response,
        db=db,
        cu=_user("advogado", "u1"),
    )
    assert chamado is True
    assert db.committed is True
    assert response.headers["deprecation"] == "true"
