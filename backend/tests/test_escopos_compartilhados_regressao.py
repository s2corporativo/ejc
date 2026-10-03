"""Exercita a segregação de carteira das listagens com dados fictícios."""
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import sqlite

from app.models.case import Case
from app.models.client import Client
from app.routers import (
    centro_custos, contratos_societarios, data_room, deadlines, fees, search, tasks,
)


@pytest.fixture
def carteira():
    with sqlite3.connect(":memory:") as db:
        db.executescript("""
            CREATE TABLE cases (id TEXT, client_id TEXT, deleted_at TEXT,
                advogado_responsavel_id TEXT, advogado_auxiliar_id TEXT);
            CREATE TABLE clients (id TEXT, responsavel_id TEXT, deleted_at TEXT);
            INSERT INTO cases VALUES
                ('responsavel', 'vinculado', NULL, 'equipe', 'outro'),
                ('auxiliar', 'aux-vinculado', NULL, 'outro', 'equipe'),
                ('alheio', 'alheio', NULL, 'outro', NULL),
                ('orfao', 'orfao', NULL, NULL, NULL),
                ('excluido', 'excluido', '2026-01-01', 'equipe', NULL);
            INSERT INTO clients VALUES
                ('direto', 'equipe', NULL), ('vinculado', 'outro', NULL),
                ('aux-vinculado', 'outro', NULL), ('alheio', 'outro', NULL),
                ('orfao', 'outro', NULL), ('excluido', 'outro', NULL),
                ('cliente-excluido', 'equipe', '2026-01-01');
        """)
        yield db


def _ids(db, model, escopo):
    stmt = select(model.id).where(model.id.in_(escopo))
    sql = str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    return {row[0] for row in db.execute(sql)}


@pytest.mark.parametrize("escopo", [
    search._ids_casos_do_usuario, fees._ids_casos_do_usuario,
    deadlines._ids_casos_do_usuario, centro_custos._ids_casos_visiveis,
    tasks._ids_casos_do_usuario, data_room._ids_casos_visiveis,
    contratos_societarios._ids_casos_do_usuario,
])
def test_caso_so_do_responsavel_ou_auxiliar_ativo(carteira, escopo):
    assert _ids(carteira, Case, escopo(SimpleNamespace(id="equipe"))) == {
        "responsavel", "auxiliar",
    }


@pytest.mark.parametrize("escopo", [
    data_room._ids_clientes_visiveis, contratos_societarios._ids_clientes_do_usuario,
])
def test_cliente_so_direto_ou_vinculado_a_caso_ativo(carteira, escopo):
    assert _ids(carteira, Client, escopo(SimpleNamespace(id="equipe"))) == {
        "direto", "vinculado", "aux-vinculado",
    }
