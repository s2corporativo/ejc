"""Auditoria RAG — reconstrução do seed de súmulas (13 de 27 verbetes
originais estavam errados: número certo com conteúdo de outra súmula,
conteúdo desatualizado/revogado, ou situação cancelada/suspensa não
sinalizada). Cada verbete foi reconferido individualmente contra fonte
oficial (STF/STJ/TST) — ver sumulas_ingestion.SUMULAS_SEED/DATA_CONFERENCIA.

Estes testes travam o contrato do seed reconstruído:
  - súmula 'ativa' vira tese status='ativa' E entra no RAG (extra.conferido=true);
  - súmula 'cancelada'/'suspensa' vira tese status='arquivada' e NÃO entra no
    RAG buscável (só registro histórico em `teses`);
  - chave_origem é determinística (tribunal:numero), não mais UUID aleatório;
  - o gate de quarentena do ai_service só libera doc marcado conferido=true.

Requer Postgres com pg_trgm + pgvector e migrations aplicadas (RUN_DB_TESTS=1).
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.services.sumulas_ingestion import SUMULAS_SEED, _titulo, ingerir_sumulas_seed

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres+pgvector com migrations (defina RUN_DB_TESTS=1)",
)

_TODOS_OS_TITULOS = [_titulo(s) for s in SUMULAS_SEED]


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste(monkeypatch):
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)
    yield
    from app.core.database import engine
    await engine.dispose()


async def _limpar(db, titulos=_TODOS_OS_TITULOS):
    """Remove os verbetes do seed (default: TODOS — ingerir_sumulas_seed
    insere o dataset inteiro de uma vez, não é seletivo por título)."""
    await db.execute(text("DELETE FROM teses WHERE titulo = ANY(:t)"), {"t": titulos})
    await db.execute(text(
        "DELETE FROM knowledge_docs WHERE chave_origem LIKE 'sumula:%' "
        "AND titulo = ANY(:t)"
    ), {"t": titulos})
    await db.commit()


def test_seed_tem_situacao_valida_em_todos_os_verbetes():
    for s in SUMULAS_SEED:
        assert s.get("situacao") in (
            "ativa", "cancelada", "suspensa", "superada", "revisao"
        ), s


def test_seed_sinaliza_as_sumulas_conhecidas_como_nao_operacionais():
    """Verbetes cancelados, superados ou incompletos ficam fora do RAG."""
    por_numero = {(s["tribunal"], s.get("numero")): s for s in SUMULAS_SEED}
    assert por_numero[("TST", "256")]["situacao"] == "cancelada"
    assert por_numero[("TST", "277")]["situacao"] == "superada"
    assert por_numero[("TST", "331")]["situacao"] == "revisao"


async def test_sumula_ativa_vira_tese_ativa_e_entra_no_rag(monkeypatch):
    from app.core.database import AsyncSessionLocal

    monkeypatch.setattr(get_settings(), "RAG_SUMULAS_SEED_ENABLED", True)
    titulo = "Súmula STJ nº 297"

    async with AsyncSessionLocal() as db:
        await _limpar(db)
        try:
            await ingerir_sumulas_seed(db)

            tese = (await db.execute(text(
                "SELECT status, descricao FROM teses WHERE titulo=:t"
            ), {"t": titulo})).one()
            assert tese.status == "ativa"
            assert "instituições financeiras" in tese.descricao

            doc = (await db.execute(text(
                "SELECT chave_origem, extra->>'conferido' AS conferido "
                "FROM knowledge_docs WHERE titulo=:t"
            ), {"t": titulo})).one()
            assert doc.chave_origem == "sumula:stj:297"   # determinística
            assert doc.conferido == "true"
        finally:
            await _limpar(db)


async def test_sumula_cancelada_vira_tese_arquivada_e_nao_entra_no_rag(monkeypatch):
    """TST 256 foi cancelada (substituída pela 331) — não pode aparecer como
    doc RAG buscável, só como registro histórico em `teses`."""
    from app.core.database import AsyncSessionLocal

    monkeypatch.setattr(get_settings(), "RAG_SUMULAS_SEED_ENABLED", True)
    titulo = "Súmula TST nº 256"

    async with AsyncSessionLocal() as db:
        await _limpar(db)
        try:
            await ingerir_sumulas_seed(db)

            tese = (await db.execute(text(
                "SELECT status FROM teses WHERE titulo=:t"
            ), {"t": titulo})).one()
            assert tese.status == "arquivada"

            doc = (await db.execute(text(
                "SELECT count(*) AS n FROM knowledge_docs WHERE titulo=:t"
            ), {"t": titulo})).one()
            assert doc.n == 0, "súmula cancelada não pode virar doc RAG"
        finally:
            await _limpar(db)


async def test_sumula_superada_vira_tese_arquivada_e_nao_entra_no_rag(monkeypatch):
    """TST 277: superada pelo julgamento definitivo da ADPF 323."""
    from app.core.database import AsyncSessionLocal

    monkeypatch.setattr(get_settings(), "RAG_SUMULAS_SEED_ENABLED", True)
    titulo = "Súmula TST nº 277"

    async with AsyncSessionLocal() as db:
        await _limpar(db)
        try:
            await ingerir_sumulas_seed(db)

            tese = (await db.execute(text(
                "SELECT status FROM teses WHERE titulo=:t"
            ), {"t": titulo})).one()
            assert tese.status == "arquivada"

            doc = (await db.execute(text(
                "SELECT count(*) AS n FROM knowledge_docs WHERE titulo=:t"
            ), {"t": titulo})).one()
            assert doc.n == 0
        finally:
            await _limpar(db)


async def test_gate_quarentena_libera_conferido_e_bloqueia_nao_conferido(monkeypatch):
    """Contraprova do gate em ai_service: doc de súmula SEM extra.conferido
    continua bloqueado (ex.: resíduo de uma ingestão manual futura sem o
    marcador); COM extra.conferido=true passa, como a reconstruída."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag
    from uuid import uuid4
    import json

    monkeypatch.setattr(get_settings(), "RAG_SUMULAS_SEED_ENABLED", True)
    termo = f"zzsumconf{uuid4().hex[:10]}"

    async def _ins(db, *, titulo, chave, conferido):
        doc_id = str(uuid4())
        await db.execute(text(
            "INSERT INTO knowledge_docs (id, titulo, categoria, fonte, chave_origem, "
            "vigente, status_indexacao, extra) VALUES "
            "(:id,:t,'trabalhista','sumula',:k,true,'indexado',CAST(:e AS jsonb))"
        ), {"id": doc_id, "t": titulo, "k": chave,
            "e": json.dumps({"conferido": conferido, "rag_status": "aprovado"})})
        await db.execute(text(
            "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
            "VALUES (:id,:d,0,:c)"
        ), {"id": str(uuid4()), "d": doc_id, "c": f"verbete {termo}"})

    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="SUM_CONFERIDO", chave=f"sumula:tst:{uuid4().hex[:6]}",
                  conferido=True)
        await _ins(db, titulo="SUM_NAO_CONFERIDO", chave=f"sumula:tst:{uuid4().hex[:6]}",
                  conferido=False)
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=10, modo_or=True)
            titulos = {r["titulo"] for r in res}
            assert "SUM_CONFERIDO" in titulos, "súmula conferida deveria ser recuperável"
            assert "SUM_NAO_CONFERIDO" not in titulos, "súmula não conferida deve seguir em quarentena"
        finally:
            await db.execute(text(
                "DELETE FROM knowledge_docs WHERE titulo IN ('SUM_CONFERIDO','SUM_NAO_CONFERIDO')"
            ))
            await db.commit()
