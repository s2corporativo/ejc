"""Catálogo TPU (app/services/saneamento/tpu.py).

Regra coberta: o catálogo nasce e permanece degradado até revisão jurídica —
`cobertura` distingue classificado de pendente; `carregar_catalogo` lê
`saneamento.tpu_movimento`, semeada pela migration 154 apenas com o código
246 (único confirmado em fonte oficial).
"""
from __future__ import annotations

import os

import pytest

from app.services.saneamento.tpu import CatalogoTPU, ClasseMovimento, carregar_catalogo

# ── Lógica pura — sem banco ───────────────────────────────────────────────────


def test_de_registros_constroi_catalogo_consultavel():
    cat = CatalogoTPU.de_registros([
        {"codigo": 246, "nome": "Arquivado definitivamente", "classe": "terminativo",
         "fonte": "TJDFT"},
    ])
    assert cat.classe_de(246) is ClasseMovimento.TERMINATIVO
    assert cat.nome_de(246) == "Arquivado definitivamente"
    assert cat.terminativos == {246}


def test_codigo_ausente_e_nao_classificado_por_padrao():
    cat = CatalogoTPU()
    assert cat.classe_de(999) is ClasseMovimento.NAO_CLASSIFICADO
    assert cat.nome_de(999) == "desconhecido"


def test_classe_de_tolera_codigo_nao_numerico():
    cat = CatalogoTPU()
    assert cat.classe_de(None) is ClasseMovimento.NAO_CLASSIFICADO
    assert cat.classe_de("abc") is ClasseMovimento.NAO_CLASSIFICADO


def test_cobertura_vazia():
    assert CatalogoTPU().cobertura == {"total": 0, "classificados": 0, "pendentes": 0}


# ── Integração (Postgres, migration 154 aplicada) ────────────────────────────

_pg = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


@_pg
async def test_carregar_catalogo_ve_a_semente_da_migration():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cat = await carregar_catalogo(db)
        assert cat.classe_de(246) is ClasseMovimento.TERMINATIVO
        assert "TJDFT" in cat.movimentos[246].fonte
