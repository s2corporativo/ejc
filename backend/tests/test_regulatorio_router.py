"""BE-04: contrato do único router regulatório sem cobertura."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.routers.regulatorio import digest_semanal


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None
        self.params = None

    async def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return _Result(self.rows)


@pytest.mark.asyncio
async def test_digest_semanal_agrega_fontes_keywords_e_nao_lidos():
    db = _DB(
        [
            {
                "fonte": "DOU",
                "keyword_match": "LGPD",
                "titulo": "Alerta",
                "resumo": "Resumo do alerta",
                "link": "https://example.test/1",
                "data_publicacao": datetime(2026, 9, 21),
                "lido": False,
                "created_at": datetime(2026, 9, 21),
            },
            {
                "fonte": "DOU",
                "keyword_match": "LGPD",
                "titulo": "Segundo",
                "resumo": None,
                "link": None,
                "data_publicacao": None,
                "lido": True,
                "created_at": datetime(2026, 9, 20),
            },
        ]
    )

    resultado = await digest_semanal(dias=7, db=db)

    assert resultado["periodo_dias"] == 7
    assert resultado["total_alertas"] == 2
    assert resultado["nao_lidos"] == 1
    assert resultado["por_fonte"] == {"DOU": 2}
    assert resultado["top_keywords"] == [{"keyword": "LGPD", "qtd": 2}]
    assert len(resultado["itens_recentes"]) == 2
    assert "diario_oficial_alertas" in db.statement
    assert db.params["desde"] is not None


@pytest.mark.asyncio
async def test_digest_semanal_sem_alertas_eh_deterministico():
    resultado = await digest_semanal(dias=30, db=_DB([]))

    assert resultado["total_alertas"] == 0
    assert resultado["nao_lidos"] == 0
    assert resultado["por_fonte"] == {}
    assert resultado["top_keywords"] == []
    assert resultado["itens_recentes"] == []
