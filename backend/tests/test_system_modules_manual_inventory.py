"""Regressão do inventário de manuais no Mapa de Módulos."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routers.system_modules import mapa_modulos


class _Scalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return _Scalars(self.rows)


class _DB:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _Result(self.rows)


@pytest.mark.asyncio
async def test_mapa_reflete_chaves_reais_de_manual_ativo():
    db = _DB([" Casos/ ", "casos", None])
    request = SimpleNamespace(app=SimpleNamespace(routes=[]))

    payload = await mapa_modulos(
        request,
        db=db,
        cu=SimpleNamespace(),
    )

    modulos = {item["module_key"]: item for item in payload["modulos"]}
    assert modulos["casos"]["tem_manual"] is True
    assert modulos["dashboard"]["tem_manual"] is False
    assert payload["resumo"]["sem_manual"] == len(modulos) - 1

    sql = str(db.statement)
    assert "module_help.module_key" in sql
    assert "module_help.ativo IS true" in sql


@pytest.mark.asyncio
async def test_mapa_nao_inventa_manual_quando_banco_esta_vazio():
    request = SimpleNamespace(app=SimpleNamespace(routes=[]))

    payload = await mapa_modulos(
        request,
        db=_DB([]),
        cu=SimpleNamespace(),
    )

    assert payload["resumo"]["sem_manual"] == payload["resumo"]["total"]
    assert all(not item["tem_manual"] for item in payload["modulos"])
