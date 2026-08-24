"""Radar Jurisprudencial — persistência do alerta (PR 4, Commit 2).

`registrar_alerta` grava `TeseAlertaJurisprudencial` a partir do resultado da
Camada 1 (`avaliar_decisao`), com dedup por `chave_dedup` — o que mais importa
cobrir aqui é a idempotência (reprocessar a mesma decisão não duplica) e a
composição da severidade do alerta a partir das teses afetadas.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.tese_extensoes import TeseAlertaJurisprudencial
from app.services.radar_jurisprudencial_registro import registrar_alerta

_TABELAS = [TeseAlertaJurisprudencial.__table__]


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _decisao(**overrides):
    base = {
        "titulo": "REsp 1.111.111/SP", "ementa": "Ementa de exemplo.",
        "tribunal": "STJ", "numero_processo": "REsp 1.111.111/SP",
        "data_julgamento": "2026-08-01", "link": "https://stj.jus.br/x",
        "fonte": "lexml",
    }
    base.update(overrides)
    return base


def _teses_afetadas(*, severidade="alta"):
    return [{"tese_id": "t1", "titulo": "Tese X", "score": 90,
              "termos_casados": ["responsabilidade"], "citacoes_casadas": [],
              "severidade": severidade, "area_alinhada": True}]


async def test_registra_alerta_novo(db):
    resultado = await registrar_alerta(
        db, _decisao(), _teses_afetadas(), chave_origem="julgado:STJ:123",
    )
    assert resultado["status"] == "criado"
    assert resultado["alerta_id"]

    alerta = (await db.execute(select(TeseAlertaJurisprudencial))).scalar_one()
    assert alerta.chave_dedup == "radar:julgado:STJ:123"
    assert alerta.severidade == "alta"
    assert alerta.status == "novo"
    assert alerta.teses_afetadas == _teses_afetadas()
    assert alerta.tribunal == "STJ"
    assert alerta.data_julgamento.isoformat() == "2026-08-01"


async def test_dedup_por_chave_origem_nao_duplica(db):
    r1 = await registrar_alerta(
        db, _decisao(), _teses_afetadas(), chave_origem="julgado:STJ:123",
    )
    r2 = await registrar_alerta(
        db, _decisao(ementa="Reformatada, mesma decisão"), _teses_afetadas(),
        chave_origem="julgado:STJ:123",
    )
    assert r1["status"] == "criado"
    assert r2["status"] == "duplicado"
    assert r2["alerta_id"] == r1["alerta_id"]

    total = (await db.execute(select(TeseAlertaJurisprudencial))).scalars().all()
    assert len(total) == 1


async def test_decisoes_diferentes_geram_alertas_distintos(db):
    r1 = await registrar_alerta(
        db, _decisao(), _teses_afetadas(), chave_origem="julgado:STJ:123",
    )
    r2 = await registrar_alerta(
        db, _decisao(), _teses_afetadas(), chave_origem="julgado:STJ:456",
    )
    assert r1["alerta_id"] != r2["alerta_id"]

    total = (await db.execute(select(TeseAlertaJurisprudencial))).scalars().all()
    assert len(total) == 2


async def test_sem_teses_afetadas_nao_grava_nada(db):
    resultado = await registrar_alerta(
        db, _decisao(), [], chave_origem="julgado:STJ:123",
    )
    assert resultado == {"status": "sem_teses_afetadas", "alerta_id": None}

    total = (await db.execute(select(TeseAlertaJurisprudencial))).scalars().all()
    assert total == []


async def test_severidade_do_alerta_e_a_mais_grave_entre_as_teses(db):
    teses = [
        {"tese_id": "t1", "titulo": "Tese A", "score": 60,
         "termos_casados": [], "citacoes_casadas": [], "severidade": "baixa",
         "area_alinhada": False},
        {"tese_id": "t2", "titulo": "Tese B", "score": 95,
         "termos_casados": [], "citacoes_casadas": [{"tipo": "sumula", "trecho": "x"}],
         "severidade": "critica", "area_alinhada": True},
        {"tese_id": "t3", "titulo": "Tese C", "score": 70,
         "termos_casados": [], "citacoes_casadas": [], "severidade": "media",
         "area_alinhada": False},
    ]
    resultado = await registrar_alerta(
        db, _decisao(), teses, chave_origem="julgado:STJ:789",
    )
    alerta = (await db.execute(
        select(TeseAlertaJurisprudencial).where(
            TeseAlertaJurisprudencial.id == resultado["alerta_id"]
        )
    )).scalar_one()
    assert alerta.severidade == "critica"


async def test_data_julgamento_malformada_vira_none(db):
    resultado = await registrar_alerta(
        db, _decisao(data_julgamento="nao e uma data"), _teses_afetadas(),
        chave_origem="julgado:STJ:999",
    )
    alerta = (await db.execute(
        select(TeseAlertaJurisprudencial).where(
            TeseAlertaJurisprudencial.id == resultado["alerta_id"]
        )
    )).scalar_one()
    assert alerta.data_julgamento is None


async def test_fonte_ausente_usa_fallback_radar_jurisprudencial(db):
    resultado = await registrar_alerta(
        db, _decisao(fonte=None), _teses_afetadas(), chave_origem="julgado:STJ:111",
    )
    alerta = (await db.execute(
        select(TeseAlertaJurisprudencial).where(
            TeseAlertaJurisprudencial.id == resultado["alerta_id"]
        )
    )).scalar_one()
    assert alerta.fonte == "radar_jurisprudencial"
