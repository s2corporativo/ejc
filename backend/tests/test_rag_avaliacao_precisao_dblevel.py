"""Auditoria RAG — harness de avaliação Hit@k/MRR (scripts/avaliar_rag_precisao.py)
como regressão automatizada.

A auditoria original apontou a ausência de qualquer métrica de qualidade de
recuperação ("não encontrei precisão@k, recall, cobertura ou freshness SLO").
Este teste semeia o gabarito verificado (as 27 súmulas reconstruídas —
ver sumulas_ingestion.py) e falha se o Hit@5/MRR cair abaixo de um piso —
detectando regressão introduzida por mudança futura no filtro/chunker/query
do RAG, mesmo sem link com nenhum PR específico.

Baseline observado nesta sessão (caminho TEXTUAL/ILIKE — embeddings
desligados, determinístico e sem custo de baixar modelo em CI): Hit@5=47,6%,
MRR=0,202 em 21 perguntas. Limiar do teste fica ABAIXO do baseline (margem
de segurança contra variância) — o objetivo é pegar queda REAL de qualidade,
não flutuação de rank por 1 posição.

Requer Postgres com pg_trgm + pgvector e migrations aplicadas (RUN_DB_TESTS=1).
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from scripts.avaliar_rag_precisao import QUESTOES, avaliar
from app.eval import retrieval_juridico_eval as gold_eval
from app.services.sumulas_ingestion import SUMULAS_SEED, _titulo, ingerir_sumulas_seed

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres+pgvector com migrations (defina RUN_DB_TESTS=1)",
)

_TODOS_OS_TITULOS = [_titulo(s) for s in SUMULAS_SEED]


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _limpar(db):
    await db.execute(text("DELETE FROM teses WHERE titulo = ANY(:t)"), {"t": _TODOS_OS_TITULOS})
    await db.execute(text(
        "DELETE FROM knowledge_docs WHERE chave_origem LIKE 'sumula:%' "
        "AND titulo = ANY(:t)"
    ), {"t": _TODOS_OS_TITULOS})
    await db.commit()


def test_gabarito_cobre_todas_as_sumulas_ativas_indexadas():
    """Sanity check do próprio harness: toda pergunta do gabarito aponta para
    um título que de fato existe no seed (evita gabarito referenciando súmula
    renomeada/removida silenciosamente)."""
    titulos_seed = set(_TODOS_OS_TITULOS)
    for q in QUESTOES:
        assert q.titulo_esperado in titulos_seed, (
            f"gabarito referencia título fora do seed: {q.titulo_esperado!r}")


async def test_hit_rate_e_mrr_acima_do_piso_de_regressao(monkeypatch):
    from app.core.database import AsyncSessionLocal
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "RAG_SUMULAS_SEED_ENABLED", True)

    async with AsyncSessionLocal() as db:
        await _limpar(db)
        try:
            resumo = await ingerir_sumulas_seed(db)
            assert resumo["indexadas_rag"] > 0, "seed não indexou nada no RAG — harness não mede nada"

            resultado = await avaliar(k=5)

            # Piso de regressão: abaixo do baseline observado (47,6% / 0,202),
            # com margem para não flakar em variação de 1-2 perguntas.
            assert resultado["hit_rate"] >= 0.30, (
                f"Hit@5 caiu para {resultado['hit_rate']:.1%} (piso 30%) — "
                f"possível regressão na recuperação RAG. Detalhes: {resultado['detalhes']}")
            assert resultado["mrr"] >= 0.12, (
                f"MRR caiu para {resultado['mrr']:.3f} (piso 0.12) — "
                f"possível regressão na recuperação RAG.")
        finally:
            await _limpar(db)


async def test_gold_set_juridico_hit_rate_e_mrr_acima_do_piso(monkeypatch):
    """Regressão do RAG contra o gold set jurídico VERSIONADO
    (app/eval/gold_set_retrieval_juridico.jsonl), avaliado por
    retrieval_juridico_eval. Mesmo piso conservador do gabarito de súmulas
    (Hit@5>=30% / MRR>=0.12), abaixo do baseline observado.

    O gold set é misto (súmulas + lei seca do planalto). Aqui só semeamos as
    súmulas (determinístico/offline); os itens de lei viram SKIP pelo gate de
    presença — o piso mede retrieval, não seed faltando. Rodar o CLI contra um
    banco de produção (com o planalto semeado) pontua também as leis."""
    from app.core.database import AsyncSessionLocal
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "RAG_SUMULAS_SEED_ENABLED", True)

    async with AsyncSessionLocal() as db:
        await _limpar(db)
        try:
            resumo = await ingerir_sumulas_seed(db)
            assert resumo["indexadas_rag"] > 0, "seed não indexou nada no RAG — harness não mede nada"

            resultado = await gold_eval.avaliar(db, k=5)

            # As 16 súmulas do gold set precisam estar presentes/pontuadas; as 3
            # leis são puladas (planalto não é semeado em CI) e não distorcem o piso.
            assert resultado["avaliados"] >= 10, (
                f"gold set pontuou só {resultado['avaliados']} itens — súmulas não "
                f"semeadas? Detalhes: {resultado['detalhes']}")
            assert resultado["hit_rate"] >= 0.30, (
                f"Hit@5={resultado['hit_rate']:.1%} (piso 30%) sobre {resultado['avaliados']} "
                f"itens — possível regressão na recuperação RAG. Detalhes: {resultado['detalhes']}")
            assert resultado["mrr"] >= 0.12, (
                f"MRR={resultado['mrr']:.3f} (piso 0.12) — possível regressão na recuperação RAG.")
        finally:
            await _limpar(db)
