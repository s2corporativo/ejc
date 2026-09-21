"""W7 (§10) — revogação de link público do Data Room fecha o ciclo do grant HMAC.

A auditoria exige "testes de grants HMAC" na promoção da W7. Os grants
criptográficos já têm provas dedicadas (test_data_room_public_download.py:
vínculo a link/arquivo/acesso/expiração). Faltava o elo de RENÚNCIA: um link
revogado (``ativo=False`` pelo endpoint de revogação) nunca pode ser servido —
o grant em si continua válido matematicamente, mas a consulta do link público
filtra ``ativo`` ANTES de qualquer uso do grant.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import anyio
import pytest
from fastapi import HTTPException
from sqlalchemy import Select

from app.models.data_room import DataRoom, DataRoomLink
from app.models.user import UserRole
from app.routers import data_room
from app.services import data_room_public as public


class _CapturaDB:
    """execute() que captura statements e devolve resultados em fila."""

    def __init__(self, resultados: list[Any] | None = None):
        self.statements: list[Any] = []
        self._resultados = list(resultados or [])
        self.commits = 0

    async def execute(self, stmt, *a, **k):
        self.statements.append(stmt)
        fila = self._resultados

        class _R:
            def scalar_one_or_none(self):
                return fila.pop(0) if fila else None

        return _R()

    def add(self, obj):
        pass

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass


def _gestao() -> SimpleNamespace:
    return SimpleNamespace(id="socio-1", role=UserRole.socio, full_name="Sócio")


def test_consulta_de_link_publico_filtra_ativo():
    """O predicado ativo.is_(True) está NA query — link revogado não é servido."""
    db = _CapturaDB()  # fila vazia = como se o link estivesse revogado no banco

    async def _call():
        await public._link_por_token(db, "token-revogado")

    with pytest.raises(HTTPException) as e:
        anyio.run(_call)

    assert e.value.status_code == 404
    assert "revogado" in str(e.value.detail).lower()
    assert any(
        isinstance(s, Select) and (w := getattr(s, "whereclause", None)) is not None and "ativo" in str(w.compile())
        for s in db.statements
    )


def test_grant_hmac_nao_burla_revogacao():
    """Grant criptograficamente válido NÃO serve link revogado: a porta de
    entrada é a consulta que filtra ativo (prova anterior) — o grant é a
    segunda barreira (vínculo ao acesso/arquivo), nunca a primeira."""
    db = _CapturaDB()
    exp = 4102444800  # 2100 — grant sem risco de expirar neste teste
    grant = public.gerar_grant("link-1", "arquivo-1", 1, exp)
    assert public.grant_valido(
        grant,
        link_id="link-1",
        arquivo_id="arquivo-1",
        acesso_numero=1,
        exp=exp,
        agora=datetime.fromtimestamp(exp, tz=timezone.utc),
    )

    async def _call():
        await public._link_por_token(db, "token-do-link-revogado")

    with pytest.raises(HTTPException) as e:
        anyio.run(_call)
    assert e.value.status_code == 404


def test_revogar_link_desativa_registro_e_commita():
    room_id, link_id = str(uuid4()), str(uuid4())
    room = DataRoom(id=room_id, nome="Sala", descricao="d")
    link = DataRoomLink(id=link_id, data_room_id=room_id, token_hash="x", ativo=True)
    db = _CapturaDB([room, link])

    async def _call():
        await data_room.revogar_link(room_id, link_id, db=db, cu=_gestao())

    anyio.run(_call)
    assert link.ativo is False
    assert db.commits == 1
