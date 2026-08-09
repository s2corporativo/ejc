from __future__ import annotations

import pytest

from app.services import rag_coverage


def test_filtro_mg_jec_inclui_categorias_dedicadas_e_tjmg_generico():
    filtro = rag_coverage._filtro_mg_jec()
    assert "jurisprudencia_tjmg_acordaos" in filtro
    assert "jurisprudencia_tjmg_juizados" in filtro
    assert "sentencas_jec_tjmg" in filtro
    assert "fonaje_enunciados" in filtro
    assert "datajud_metadados" in filtro
    assert "source_family" in filtro
    assert "lower(kd.categoria) = 'jurisprudencia'" in filtro
    assert "TJMG" in filtro


def test_colecao_logica_mapeia_tjmg_automatico_sem_mudar_categoria_fisica():
    expr = rag_coverage._SQL_COLECAO
    assert "jurisprudencia_tjmg_acordaos_auto" in expr
    assert "kd.categoria" in expr
    assert "collection" in expr


def test_fonte_validada_nao_faz_cast_booleano_arriscado():
    expr = rag_coverage._SQL_FONTE_VALIDADA
    assert "::boolean" not in expr
    assert "fonte_validada" in expr
    assert "= 'true'" in expr


class _Mappings:
    def __init__(self, *, first=None, rows=None):
        self._first = first
        self._rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self):
        self.calls = 0
        self.sql = []

    async def execute(self, stmt, params=None):
        self.calls += 1
        self.sql.append(str(stmt))
        if self.calls == 1:
            return _Mappings(
                first={
                    "documentos": 10,
                    "chunks": 24,
                    "documentos_indexados": 9,
                    "documentos_aprovados": 8,
                    "fonte_validada_explicita": 6,
                    "ultima_atualizacao": None,
                }
            )
        if self.calls == 2:
            return _Mappings(
                rows=[
                    {
                        "colecao": "jurisprudencia_tjmg_acordaos_auto",
                        "documentos": 4,
                        "chunks": 12,
                        "indexados": 4,
                        "aprovados": 4,
                        "fonte_validada_explicita": 0,
                        "ultima_atualizacao": None,
                    }
                ]
            )
        return _Mappings(rows=[{"valor": "x", "documentos": 2}])


@pytest.mark.asyncio
async def test_medicao_retorna_somente_agregados_e_marca_metodologia():
    db = _FakeDB()
    out = await rag_coverage.medir_cobertura_rag(db, mg_jec_only=True)

    assert out["escopo"] == "mg_jec"
    assert out["documentos"] == 10
    assert out["chunks"] == 24
    assert out["pct_fonte_validada_explicita"] == 60.0
    assert out["colecoes"][0]["colecao"] == "jurisprudencia_tjmg_acordaos_auto"
    assert out["metodologia"]["tjmg_generico_mapeado_sem_duplicacao"] is True
    assert out["metodologia"]["conteudo_exposto"] is False
    assert db.calls == 7

    # O serviço agrega metadata; não seleciona título/conteúdo do corpus.
    sql = "\n".join(db.sql).lower()
    assert "kc.conteudo" not in sql
    assert "kd.titulo" not in sql
