from __future__ import annotations

import pytest


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Resultado:
    def __init__(self, *, total=None, rows=None):
        self._total = total
        self._rows = rows or []

    def scalar_one(self):
        return self._total

    def scalars(self):
        return _ScalarRows(self._rows)


class _DBSomenteLeitura:
    def __init__(self):
        self.consultas: list[tuple[str, dict]] = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        parametros = dict(params or {})
        self.consultas.append((sql, parametros))
        if sql.startswith("SELECT COUNT(*) FROM ("):
            return _Resultado(total=250)
        return _Resultado(rows=[f"id-{indice:03d}" for indice in range(100)])


@pytest.mark.asyncio
async def test_achado_conta_exato_e_limita_ids_no_banco():
    from app.services.integridade_service import LIMITE_IDS, _achado

    db = _DBSomenteLeitura()
    resultado = await _achado(
        db,
        tipo="peca_de_caso_excluido",
        sql="SELECT id FROM legal_docs ORDER BY id",
        entidade="legal_docs",
        entidade_pai="cases",
        estado_pai="excluido",
        severidade="alta",
        acao_recomendada="Conferir.",
    )

    assert resultado["total"] == 250
    assert len(resultado["ids"]) == LIMITE_IDS == 100
    assert resultado["truncado"] is True

    assert len(db.consultas) == 2
    sql_contagem, params_contagem = db.consultas[0]
    sql_ids, params_ids = db.consultas[1]

    assert "SELECT COUNT(*) FROM ( SELECT id FROM legal_docs ORDER BY id )" in sql_contagem
    assert "LIMIT :_limite_ids" in sql_ids
    assert params_contagem == {}
    assert params_ids["_limite_ids"] == LIMITE_IDS
