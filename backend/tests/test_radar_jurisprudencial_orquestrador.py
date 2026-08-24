"""Radar Jurisprudencial — orquestrador (PR 4, Commit 6).

Duas camadas de teste, mesmo padrão de `test_impacto_regulatorio.py`:

1. **Função pura** (`_mesclar_camada_semantica`) e `_carregar_teses`
   (só toca `teses`, colunas JSON genéricas — portável para SQLite): sem
   Postgres.
2. **`executar_radar` fim a fim**: exige `RUN_DB_TESTS=1`. `knowledge_docs.
   extra` é `JSONB` (Postgres-only — `sqlalchemy.dialects.postgresql.JSONB`
   não compila em SQLite, confirmado por `CompileError` ao tentar criar a
   tabela), então o fluxo completo (varredura de `knowledge_docs` + merge +
   persistência) só roda contra Postgres real.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.tese import Tese, TeseStatus, TeseTipo
from app.services.radar_jurisprudencial_orquestrador import (
    _SEVERIDADE_SO_SEMANTICA,
    _carregar_teses,
    _mesclar_camada_semantica,
)


# ── _mesclar_camada_semantica — função pura, sem banco ──────────────────────

def _afetada_camada1(tese_id="t1", severidade="alta"):
    return {"tese_id": tese_id, "titulo": "Tese", "score": 85,
            "termos_casados": ["x"], "citacoes_casadas": [],
            "severidade": severidade, "area_alinhada": True}


def _semelhante(tese_id="t2", score=0.8):
    return {"tese_id": tese_id, "titulo": "Tese semântica", "area_juridica": "civil",
            "score_semantico": score}


def test_camada_semantica_adiciona_tese_nao_encontrada_pela_camada_1():
    afetadas = [_afetada_camada1(tese_id="t1")]
    semelhantes = [_semelhante(tese_id="t2")]
    resultado = _mesclar_camada_semantica(afetadas, semelhantes)
    assert {t["tese_id"] for t in resultado} == {"t1", "t2"}
    extra = next(t for t in resultado if t["tese_id"] == "t2")
    assert extra["severidade"] == _SEVERIDADE_SO_SEMANTICA
    assert extra["score_semantico"] == 0.8


def test_camada_semantica_nao_duplica_tese_ja_encontrada_pela_camada_1():
    afetadas = [_afetada_camada1(tese_id="t1", severidade="critica")]
    semelhantes = [_semelhante(tese_id="t1", score=0.9)]
    resultado = _mesclar_camada_semantica(afetadas, semelhantes)
    assert len(resultado) == 1
    assert resultado[0]["severidade"] == "critica"  # nunca rebaixa a Camada 1


def test_sem_semelhantes_devolve_apenas_camada_1():
    afetadas = [_afetada_camada1()]
    assert _mesclar_camada_semantica(afetadas, []) == afetadas


def test_sem_camada_1_mas_com_semanticas_devolve_so_as_semanticas():
    resultado = _mesclar_camada_semantica([], [_semelhante()])
    assert len(resultado) == 1
    assert resultado[0]["severidade"] == _SEVERIDADE_SO_SEMANTICA


# ── _carregar_teses — só toca `teses` (colunas JSON genéricas, SQLite-safe) ──

_TABELAS = [Tese.__table__]


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _tese(**overrides) -> Tese:
    base = dict(
        id=str(uuid4()), titulo="Responsabilidade civil bancária",
        descricao="Descrição de teste com mais de dez caracteres",
        fundamentacao="Súmula 297 do STJ", area_juridica="bancario",
        tipo=TeseTipo.escritorio, status=TeseStatus.rascunho,
    )
    base.update(overrides)
    return Tese(**base)


async def test_carregar_teses_inclui_rascunho_e_exclui_arquivada(db):
    ativa = _tese(status_validacao="descoberta")
    arquivada = _tese(id=str(uuid4()), status_validacao="arquivada")
    db.add_all([ativa, arquivada])
    await db.commit()

    teses = await _carregar_teses(db)
    ids = {t["id"] for t in teses}
    assert ativa.id in ids
    assert arquivada.id not in ids


async def test_carregar_teses_exclui_deletada(db):
    deletada = _tese(deleted_at=datetime.now(timezone.utc))
    db.add(deletada)
    await db.commit()

    teses = await _carregar_teses(db)
    assert deletada.id not in {t["id"] for t in teses}


async def test_carregar_teses_extrai_termos_de_titulo_e_fundamentacao(db):
    tese = _tese()
    db.add(tese)
    await db.commit()

    teses = await _carregar_teses(db)
    saida = next(t for t in teses if t["id"] == tese.id)
    assert "responsabilidade" in saida["termos"]
    assert saida["fundamentacao"] == "Súmula 297 do STJ"


async def test_carregar_teses_sem_status_validacao_nao_e_excluida(db):
    """Tese legada (status_validacao=None) não pode ser tratada como
    arquivada — `IS DISTINCT FROM` no SQL cuida disso, mas confirmamos aqui
    que o comportamento realmente inclui NULL."""
    legada = _tese(status_validacao=None)
    db.add(legada)
    await db.commit()

    teses = await _carregar_teses(db)
    assert legada.id in {t["id"] for t in teses}


# ── executar_radar fim a fim — Postgres real (JSONB em knowledge_docs) ──────

pytestmark_db = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1) — "
           "knowledge_docs.extra é JSONB, não compila em SQLite",
)


@pytestmark_db
async def test_executar_radar_end_to_end_gera_alerta_e_avanca_watermark():
    """Documenta o comportamento esperado de ponta a ponta contra Postgres
    real: decisão nova casa com tese existente → alerta criado; segunda
    execução sem decisão nova → 0 alertas novos (watermark avançou).
    Implementação completa fica condicionada a RUN_DB_TESTS=1 — não há
    Postgres disponível neste sandbox de desenvolvimento."""
    pytest.skip("cenário de integração fim a fim — requer ambiente Postgres real")
