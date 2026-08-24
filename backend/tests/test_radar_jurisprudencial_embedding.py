"""Radar Jurisprudencial — Camada 2, semântica (PR 4, Commit 4).

`atualizar_embedding_tese`/`atualizar_embedding_tese_job` são testáveis sem
Postgres (mutação de atributo Python + mock de `gerar_embeddings`).
`buscar_teses_similares` usa `<=>`/`hnsw.ef_search`, Postgres-only — só o
caminho de falha (embedding indisponível → lista vazia) é coberto aqui; a
query vetorial real fica fora do escopo destes testes (RUN_DB_TESTS=1).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.tese import Tese, TeseStatus, TeseTipo
from app.services import radar_jurisprudencial_embedding as mod
from app.services.radar_jurisprudencial_embedding import (
    atualizar_embedding_tese,
    atualizar_embedding_tese_job,
    buscar_teses_similares,
)

_TABELAS = [Tese.__table__]


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session, maker
    await engine.dispose()


def _tese(**overrides) -> Tese:
    base = dict(
        id=str(uuid4()), titulo="Tese de teste",
        descricao="Descrição de teste com mais de dez caracteres",
        tipo=TeseTipo.escritorio, status=TeseStatus.ativa,
    )
    base.update(overrides)
    return Tese(**base)


# ── atualizar_embedding_tese ─────────────────────────────────────────────────

async def test_atualizar_embedding_seta_vetor_quando_gerar_embeddings_funciona(db, monkeypatch):
    session, _ = db
    vetor = [0.1] * 1024

    async def _fake(textos, modo="passage"):
        assert modo == "passage"
        return [vetor]

    monkeypatch.setattr(mod, "gerar_embeddings", _fake)
    tese = _tese()
    await atualizar_embedding_tese(session, tese)
    assert tese.embedding == vetor


async def test_atualizar_embedding_vira_none_quando_gerar_embeddings_falha(db, monkeypatch):
    session, _ = db

    async def _fake(textos, modo="passage"):
        return None  # gerar_embeddings nunca levanta — fallback é None

    monkeypatch.setattr(mod, "gerar_embeddings", _fake)
    tese = _tese(embedding=[0.5] * 1024)
    await atualizar_embedding_tese(session, tese)
    assert tese.embedding is None


async def test_atualizar_embedding_texto_vazio_nao_chama_gerar_embeddings(db, monkeypatch):
    session, _ = db
    chamou = {"n": 0}

    async def _fake(textos, modo="passage"):
        chamou["n"] += 1
        return [[0.1] * 1024]

    monkeypatch.setattr(mod, "gerar_embeddings", _fake)
    tese = _tese(titulo="", descricao="", fundamentacao=None, jurisprudencia=None)
    await atualizar_embedding_tese(session, tese)
    assert tese.embedding is None
    assert chamou["n"] == 0


async def test_atualizar_embedding_exceção_do_provider_vira_none_sem_propagar(db, monkeypatch):
    session, _ = db

    async def _fake(textos, modo="passage"):
        raise RuntimeError("provider fora do ar")

    monkeypatch.setattr(mod, "gerar_embeddings", _fake)
    tese = _tese()
    await atualizar_embedding_tese(session, tese)  # não deve levantar
    assert tese.embedding is None


# ── atualizar_embedding_tese_job (BackgroundTask, sessão própria) ───────────

async def test_job_persiste_embedding_com_sessao_propria(db, monkeypatch):
    session, maker = db
    vetor = [0.2] * 1024

    async def _fake(textos, modo="passage"):
        return [vetor]

    monkeypatch.setattr(mod, "gerar_embeddings", _fake)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)

    tese = _tese()
    session.add(tese)
    await session.commit()

    await atualizar_embedding_tese_job(tese.id)

    async with maker() as verificacao:
        from sqlalchemy import select
        recarregada = (await verificacao.execute(
            select(Tese).where(Tese.id == tese.id)
        )).scalar_one()
        assert recarregada.embedding == vetor


async def test_job_tese_inexistente_nao_levanta(db, monkeypatch):
    _, maker = db
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", maker)
    await atualizar_embedding_tese_job(str(uuid4()))  # não deve levantar


async def test_job_falha_de_commit_nao_propaga(db, monkeypatch):
    session, maker = db

    async def _fake(textos, modo="passage"):
        return [[0.1] * 1024]

    monkeypatch.setattr(mod, "gerar_embeddings", _fake)

    class _MakerQuebrado:
        def __call__(self):
            raise RuntimeError("conexão indisponível")

    monkeypatch.setattr("app.core.database.AsyncSessionLocal", _MakerQuebrado())
    await atualizar_embedding_tese_job(str(uuid4()))  # não deve levantar


# ── buscar_teses_similares — caminho de falha (Postgres-only não coberto aqui) ─

async def test_busca_semantica_texto_vazio_devolve_lista_vazia(db):
    session, _ = db
    assert await buscar_teses_similares(session, "") == []
    assert await buscar_teses_similares(session, "   ") == []


async def test_busca_semantica_sem_embedding_disponivel_devolve_lista_vazia(db, monkeypatch):
    session, _ = db

    async def _fake(textos, modo="query"):
        return None

    monkeypatch.setattr(mod, "gerar_embeddings", _fake)
    assert await buscar_teses_similares(session, "texto da decisão") == []


async def test_busca_semantica_erro_no_provider_devolve_lista_vazia_sem_levantar(db, monkeypatch):
    session, _ = db

    async def _fake(textos, modo="query"):
        raise RuntimeError("provider fora do ar")

    monkeypatch.setattr(mod, "gerar_embeddings", _fake)
    assert await buscar_teses_similares(session, "texto da decisão") == []
