"""Auditoria RAG — validação ROW-LEVEL (Postgres real) dos gates de governança,
quarentena de súmulas, exclusão do corpus fictício e do versionamento de
`chave_origem` (migration 092).

Fecha os bloqueadores P0 apontados na auditoria:
  * documento explicitamente BLOQUEADO/RECUSADO/PENDENTE nunca é recuperado;
  * súmulas do seed (fonte='sumula' / chave 'sumula:%') ficam em QUARENTENA;
  * corpus FICTÍCIO (extra.ficticio=true) é excluído das buscas amplas e só
    entra com incluir_ficticio=True (geração de peça a partir de modelos);
  * reingerir a MESMA `chave_origem` com conteúdo novo cria nova versão vigente
    sem colidir com o índice único parcial (antes: IntegrityError).

Requer Postgres com pg_trgm + pgvector e migrations aplicadas. Roda só quando
RUN_DB_TESTS=1 (job de CI `db-validation`); caso contrário, pula. Determinístico:
usa o caminho TEXTUAL (ILIKE) de buscar_contexto_rag (embeddings desligados).
"""
from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres+pgvector com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste(monkeypatch):
    """Descarta o pool do engine singleton no MESMO event loop que o usou —
    ver justificativa detalhada em test_rag_isolation_dblevel.py."""
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)
    yield
    from app.core.database import engine
    await engine.dispose()


async def _ins(db, *, titulo, categoria, conteudo, chave_origem, fonte=None, extra=None):
    """Insere doc + 1 chunk textual (caminho ILIKE, sem embeddings)."""
    doc_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO knowledge_docs (id, titulo, categoria, fonte, chave_origem, "
            "vigente, status_indexacao, extra) "
            "VALUES (:id,:t,:c,:f,:k, true, 'indexado', CAST(:e AS jsonb))"
        ),
        {"id": doc_id, "t": titulo, "c": categoria, "f": fonte, "k": chave_origem,
         "e": json.dumps(extra or {})},
    )
    await db.execute(
        text(
            "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
            "VALUES (:id, :doc, 0, :cont)"
        ),
        {"id": str(uuid4()), "doc": doc_id, "cont": conteudo},
    )
    return doc_id


async def test_gate_bloqueado_e_pendente_nao_recuperados():
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzgate{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="GATE_OK", categoria="legislacao",
                   conteudo=f"norma valida {termo}", chave_origem=f"n:{uuid4()}",
                   extra={"rag_status": "aprovado"})
        await _ins(db, titulo="GATE_BLOQUEADO", categoria="legislacao",
                   conteudo=f"norma bloqueada {termo}", chave_origem=f"b:{uuid4()}",
                   extra={"confidence_level": "bloqueado"})
        await _ins(db, titulo="GATE_RECUSADO", categoria="legislacao",
                   conteudo=f"norma recusada {termo}", chave_origem=f"r:{uuid4()}",
                   extra={"rag_status": "recusado"})
        await _ins(db, titulo="GATE_PENDENTE", categoria="legislacao",
                   conteudo=f"norma pendente {termo}", chave_origem=f"p:{uuid4()}",
                   extra={"rag_status": "pendente"})
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            titulos = {r["titulo"] for r in res}
            assert "GATE_OK" in titulos, "doc aprovado/legado deveria ser recuperado"
            assert "GATE_BLOQUEADO" not in titulos, "VAZAMENTO: doc bloqueado recuperado"
            assert "GATE_RECUSADO" not in titulos, "VAZAMENTO: doc recusado recuperado"
            assert "GATE_PENDENTE" not in titulos, "VAZAMENTO: doc pendente recuperado"
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE titulo LIKE 'GATE_%'"))
            await db.commit()


async def test_sumulas_em_quarentena_nao_recuperadas():
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzsum{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        # marcador 1: fonte='sumula'; marcador 2: chave_origem 'sumula:%'
        await _ins(db, titulo="SUMULA_FONTE", categoria="trabalhista",
                   conteudo=f"verbete sumular {termo}", chave_origem=f"x:{uuid4()}",
                   fonte="sumula")
        await _ins(db, titulo="SUMULA_CHAVE", categoria="trabalhista",
                   conteudo=f"outro verbete {termo}", chave_origem=f"sumula:{uuid4()}")
        await _ins(db, titulo="NAO_SUMULA", categoria="trabalhista",
                   conteudo=f"jurisprudencia comum {termo}", chave_origem=f"j:{uuid4()}",
                   extra={"rag_status": "aprovado"})
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            titulos = {r["titulo"] for r in res}
            assert "NAO_SUMULA" in titulos
            assert "SUMULA_FONTE" not in titulos, "quarentena falhou (fonte=sumula)"
            assert "SUMULA_CHAVE" not in titulos, "quarentena falhou (chave sumula:)"
        finally:
            await db.execute(text(
                "DELETE FROM knowledge_docs WHERE titulo IN "
                "('SUMULA_FONTE','SUMULA_CHAVE','NAO_SUMULA')"))
            await db.commit()


async def test_ficticio_excluido_por_padrao_incluido_sob_demanda():
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzfic{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="FIC_MODELO", categoria="modelo_documento_juridico",
                   conteudo=f"modelo ficticio {termo}", chave_origem=f"f:{uuid4()}",
                   extra={"ficticio": True, "rag_status": "aprovado"})
        await db.commit()
        try:
            # busca ampla (fundamentação) → fictício NÃO aparece
            amplo = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            assert "FIC_MODELO" not in {r["titulo"] for r in amplo}, (
                "corpus fictício vazou em busca ampla (fundamentação)")
            # geração de peça (opt-in) → fictício disponível como estrutura
            modelos = await buscar_contexto_rag(
                db, termo, limite=20, modo_or=True,
                categorias=["modelo_documento_juridico"], incluir_ficticio=True)
            assert "FIC_MODELO" in {r["titulo"] for r in modelos}, (
                "incluir_ficticio=True deveria liberar o corpus de modelos")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE titulo = 'FIC_MODELO'"))
            await db.commit()


async def test_regime_estrito_exclui_documento_legado_sem_aprovacao():
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzlegacy{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="LEGADO_SEM_CURADORIA", categoria="legislacao",
                   conteudo=f"norma antiga {termo}", chave_origem=f"legacy:{uuid4()}")
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            assert "LEGADO_SEM_CURADORIA" not in {r["titulo"] for r in res}
        finally:
            await db.execute(text(
                "DELETE FROM knowledge_docs WHERE titulo='LEGADO_SEM_CURADORIA'"))
            await db.commit()


async def test_verificador_citacao_usa_mesmos_gates_do_rag():
    from app.core.database import AsyncSessionLocal
    from app.services.citation_check import _existe_sumula

    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="Súmula STJ nº 997", categoria="sumula_stj",
                   conteudo="verbete oficial aprovado para teste de citação",
                   chave_origem="sumula:stj:997",
                   extra={"rag_status": "aprovado", "conferido": True})
        await _ins(db, titulo="Súmula STJ nº 998", categoria="sumula_stj",
                   conteudo="verbete ainda pendente para teste de citação",
                   chave_origem="sumula:stj:998",
                   extra={"rag_status": "pendente", "conferido": True})
        await db.commit()
        try:
            assert await _existe_sumula(db, "997", "STJ") == "Súmula STJ nº 997"
            assert await _existe_sumula(db, "998", "STJ") is None
        finally:
            await db.execute(text(
                "DELETE FROM knowledge_docs WHERE chave_origem IN "
                "('sumula:stj:997','sumula:stj:998')"))
            await db.commit()


async def test_reingestao_versiona_sem_colidir_indice_unico():
    """Bug P0: reingerir a MESMA chave_origem com conteúdo novo colidia com o
    índice único (não considerava `vigente`). Após a migration 092 + flush
    ordenado do upsert, cria nova versão vigente e preserva o histórico."""
    from app.core.database import AsyncSessionLocal
    from app.services.ingestion_service import upsert_documento

    k = f"lei:teste:{uuid4()}"
    txt1 = ("Redacao ORIGINAL da norma de teste, com tamanho suficiente para "
            "ultrapassar o minimo de cinquenta caracteres exigido pelo upsert.")
    txt2 = ("Redacao ATUALIZADA da mesma norma apos alteracao legislativa, "
            "tambem com mais de cinquenta caracteres para valer a reingestao.")
    async with AsyncSessionLocal() as db:
        r1 = await upsert_documento(db, titulo="VER v1", categoria="legislacao",
                                    conteudo=txt1, fonte="http://x", chave_origem=k,
                                    embutir_vetores=False)
        await db.commit()
    async with AsyncSessionLocal() as db:
        # NÃO pode lançar IntegrityError (era o bug)
        r2 = await upsert_documento(db, titulo="VER v2", categoria="legislacao",
                                    conteudo=txt2, fonte="http://x", chave_origem=k,
                                    embutir_vetores=False)
        await db.commit()
    async with AsyncSessionLocal() as db:
        try:
            assert r1 == "novo" and r2 == "atualizado", (r1, r2)
            rows = (await db.execute(text(
                "SELECT titulo, versao, vigente FROM knowledge_docs "
                "WHERE chave_origem=:k ORDER BY versao"), {"k": k})).all()
            assert len(rows) == 2, "as duas versões devem coexistir (histórico)"
            vig = [r for r in rows if r.vigente]
            assert len(vig) == 1, "exatamente UMA versão vigente por chave"
            assert vig[0].titulo == "VER v2", "a versão vigente deve ser a mais nova"
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE chave_origem=:k"), {"k": k})
            await db.commit()
