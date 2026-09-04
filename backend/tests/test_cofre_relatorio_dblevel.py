# -*- coding: utf-8 -*-
"""O relatório do cofre não pode quebrar por SQL fora de sincronia com o schema.

Regressão do pente fino E2E de 29/08/2026: ``GET /api/modulos/cofre/relatorio``
respondia 500 em toda chamada porque o SQL cru referenciava ``d.title``, mas a
coluna de ``documents`` é ``titulo`` (UndefinedColumnError). Nenhum teste
executava esse SQL contra o schema real — schemas Pydantic e snapshot de rotas
não pegam nome de coluna em raw-SQL.

O teste extrai o SQL de dentro da própria rota (``inspect.getsource``) e o
executa no Postgres migrado: se a consulta voltar a divergir do schema em
qualquer coluna, este teste quebra — sem depender de cópia manual do SQL.
"""
from __future__ import annotations

import inspect
import os
import re

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(
    not (os.getenv("RUN_DB_TESTS") and os.getenv("SCHEMA_CHECK_DATABASE_URL")),
    reason="requer PostgreSQL (RUN_DB_TESTS=1 e SCHEMA_CHECK_DATABASE_URL)",
)


def _sql_do_relatorio() -> str:
    from app.routers import novos_modulos

    fonte = inspect.getsource(novos_modulos.cofre_relatorio)
    m = re.search(r'text\("""(.*?)"""\)', fonte, re.DOTALL)
    assert m, "SQL do cofre_relatorio não encontrado — a rota mudou de forma?"
    return m.group(1)


def test_sql_do_relatorio_do_cofre_executa_no_schema_real():
    eng = create_engine(os.environ["SCHEMA_CHECK_DATABASE_URL"])
    with eng.begin() as conn:
        rows = conn.execute(text(_sql_do_relatorio()), {"lim": 5}).fetchall()
    # Executou sem UndefinedColumnError; com banco vazio a lista pode ser [].
    assert isinstance(rows, list)


def test_sql_do_relatorio_do_cofre_usa_titulo_e_nao_title():
    sql = _sql_do_relatorio()
    assert "d.titulo" in sql
    assert "d.title," not in sql and "d.title " not in sql
