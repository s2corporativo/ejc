"""Regressões P0 da captura DJEN — Issue #968.

Prova as invariantes que não dependem da API externa:
- resolução de casos é feita em lote;
- processo ambíguo nunca é vinculado automaticamente;
- deduplicação da comunicação é responsabilidade atômica do PostgreSQL.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.services import djen_service


def _caso(caso_id: str, numero: str):
    return SimpleNamespace(
        id=caso_id,
        numero_processo=numero,
        advogado_responsavel_id=None,
    )


def test_indexar_casos_unicos_nao_escolhe_vinculo_ambiguo():
    numero_ambiguo = "0000001-02.2020.8.13.0000"
    numero_unico = "0000002-03.2020.8.13.0000"

    unicos, ambiguos = djen_service._indexar_casos_unicos(
        [
            _caso("a", numero_ambiguo),
            _caso("b", "00000010220208130000"),
            _caso("c", numero_unico),
        ]
    )

    assert djen_service.normalizar_processo(numero_ambiguo) not in unicos
    assert unicos[djen_service.normalizar_processo(numero_unico)].id == "c"
    assert ambiguos == 1


class _ScalarResult:
    def __init__(self, casos):
        self._casos = casos

    def scalars(self):
        return self

    def all(self):
        return self._casos


class _DBContador:
    def __init__(self, casos):
        self.casos = casos
        self.execucoes = 0

    async def execute(self, _statement):
        self.execucoes += 1
        return _ScalarResult(self.casos)


@pytest.mark.asyncio
async def test_busca_de_casos_do_lote_executa_uma_unica_query():
    db = _DBContador(
        [
            _caso("a", "0000001-02.2020.8.13.0000"),
            _caso("b", "0000002-03.2020.8.13.0000"),
        ]
    )

    resultado = await djen_service.buscar_casos_ativos_por_processos(
        db,
        {
            "00000010220208130000",
            "00000020320208130000",
        },
    )

    assert db.execucoes == 1
    assert set(resultado) == {
        "00000010220208130000",
        "00000020320208130000",
    }


def test_insert_comunicacao_usa_on_conflict_do_nothing_e_returning():
    stmt = djen_service._stmt_inserir_comunicacao(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "comunicacao_id_externo": "cnj-externo-1",
            "advogado_id": "00000000-0000-0000-0000-000000000002",
            "numero_processo": "0000001-02.2020.8.13.0000",
            "tribunal": "TJMG",
            "tipo_comunicacao": "Intimação",
            "data_disponibilizacao": None,
            "texto_resumo": "conteúdo fictício",
            "case_id": None,
        }
    )
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    ).upper()

    assert "ON CONFLICT (COMUNICACAO_ID_EXTERNO) DO NOTHING" in sql
    assert "RETURNING DJEN_COMUNICACOES.ID" in sql


def test_servico_nao_faz_select_previo_por_id_externo():
    origem = open(djen_service.__file__, encoding="utf-8").read()

    assert "select(DjenComunicacao).where" not in origem
    assert ".on_conflict_do_nothing(" in origem
