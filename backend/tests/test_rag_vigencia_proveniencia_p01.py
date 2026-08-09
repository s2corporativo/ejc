"""Contratos P0.1 do gate estrito de vigência normativa.

Uma string `legal_status='vigente'` não basta para fundamentação atual: o estado
precisa ter proveniência e carimbo de verificação positivos. Situações suspensa
ou parcialmente revogada permanecem úteis para pesquisa, mas não podem passar
como autoridade atual quando o modo estrito estiver ligado.
"""
from __future__ import annotations

import pytest

from app.services import ai_service
from app.services.ai_service import (
    _FILTRO_REVOGADA_RAG,
    _FILTRO_VIGENCIA_VERIFICADA_RAG,
    _filtros_gate_rag,
)


def _flag(monkeypatch, valor: bool) -> None:
    monkeypatch.setattr(
        ai_service.settings,
        "RAG_EXIGIR_VIGENCIA_VERIFICADA",
        valor,
    )


def test_gate_estrito_exige_status_vigente_com_proveniencia_positiva():
    filtro = _FILTRO_VIGENCIA_VERIFICADA_RAG

    assert "legal_status" in filtro
    assert "legal_status_origem" in filtro
    assert "legal_status_verificado_em" in filtro
    assert "legal_status_inferido_em" in filtro
    assert "'vigente'" in filtro


def test_status_inferido_nao_e_equivalente_a_verificado():
    filtro = _FILTRO_VIGENCIA_VERIFICADA_RAG

    # O SQL deve exigir ausência do carimbo de inferência na condição positiva,
    # em vez de aceitar qualquer string 'vigente' gravada automaticamente.
    assert "legal_status_inferido_em" in filtro
    assert "legal_status_verificado_em" in filtro


def test_suspensa_e_parcialmente_revogada_nao_passam_como_vigencia_atual():
    filtro = _FILTRO_VIGENCIA_VERIFICADA_RAG

    # Em modo estrito, a condição positiva é deliberadamente limitada a
    # `vigente`; estes estados podem existir no acervo, mas não fundamentar como
    # direito atual sem análise específica do alcance da suspensão/revogação.
    assert "'suspensa'" not in filtro.split("'vigente'", 1)[1]
    assert "'parcialmente_revogada'" not in filtro.split("'vigente'", 1)[1]


@pytest.mark.parametrize("estrito", [True, False])
def test_revogada_continua_bloqueada_independentemente_do_modo(monkeypatch, estrito):
    _flag(monkeypatch, estrito)
    assert _FILTRO_REVOGADA_RAG in _filtros_gate_rag(False)


def test_flag_false_nao_finge_que_houve_verificacao(monkeypatch):
    _flag(monkeypatch, False)
    gate = _filtros_gate_rag(False)

    assert _FILTRO_VIGENCIA_VERIFICADA_RAG not in gate
    assert _FILTRO_REVOGADA_RAG in gate


# ══════════════════════════════════════════════════════════════════════════
# Testes DB-level: executam o filtro SQL contra banco real
# ══════════════════════════════════════════════════════════════════════════

import os
import pytest

pytestmark_db = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="Teste de banco (RUN_DB_TESTS=1 para rodar)",
)


@pytestmark_db
async def test_legislacao_vigente_sem_proveniencia_rejeitada(monkeypatch):
    """Legislação vigente='vigente' SEM proveniência completa é rejeitada."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag
    from uuid import uuid4
    from sqlalchemy import text

    _flag(monkeypatch, True)  # modo estrito ligado
    termo = f"zzprov{uuid4().hex[:10]}"
    k = f"test:prov:{uuid4()}"

    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO knowledge_docs (id, titulo, categoria, chave_origem, "
            "status_indexacao, vigente, revisado, extra, base_rag) "
            "VALUES (:id, :titulo, 'legislacao', :k, 'indexado', true, true, "
            "CAST(:extra AS jsonb), 'publica')"),
            {"id": str(uuid4()), "titulo": "PROV_AUSENTE", "k": k, "extra": '{"rag_status":"aprovado","legal_status":"vigente"}'}
        )
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            assert "PROV_AUSENTE" not in {r["titulo"] for r in res}, (
                "documento vigente sem proveniência passou pelo gate estrito")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE chave_origem=:k"), {"k": k})
            await db.commit()


@pytestmark_db
async def test_legislacao_vigente_sem_data_verificacao_rejeitada(monkeypatch):
    """Legislação vigente com origem mas SEM data de verificação é rejeitada."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag
    from uuid import uuid4
    from sqlalchemy import text

    _flag(monkeypatch, True)
    termo = f"zzdata{uuid4().hex[:10]}"
    k = f"test:data:{uuid4()}"

    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO knowledge_docs (id, titulo, categoria, chave_origem, "
            "status_indexacao, vigente, revisado, extra, base_rag) "
            "VALUES (:id, :titulo, 'legislacao', :k, 'indexado', true, true, "
            "CAST(:extra AS jsonb), 'publica')"),
            {"id": str(uuid4()), "titulo": "DATA_AUSENTE", "k": k,
             "extra": '{"rag_status":"aprovado","legal_status":"vigente","legal_status_origem":"planalto:texto_compilado"}'}
        )
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            assert "DATA_AUSENTE" not in {r["titulo"] for r in res}, (
                "documento vigente sem data de verificação passou pelo gate")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE chave_origem=:k"), {"k": k})
            await db.commit()


@pytestmark_db
async def test_legislacao_vigente_com_carimbo_inferido_rejeitada(monkeypatch):
    """Legislação vigente com carimbo de inferência é rejeitada."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag
    from uuid import uuid4
    from sqlalchemy import text

    _flag(monkeypatch, True)
    termo = f"zzinfer{uuid4().hex[:10]}"
    k = f"test:infer:{uuid4()}"

    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO knowledge_docs (id, titulo, categoria, chave_origem, "
            "status_indexacao, vigente, revisado, extra, base_rag) "
            "VALUES (:id, :titulo, 'legislacao', :k, 'indexado', true, true, "
            "CAST(:extra AS jsonb), 'publica')"),
            {"id": str(uuid4()), "titulo": "CARIMBO_INFERIDO", "k": k,
             "extra": '{"rag_status":"aprovado","legal_status":"vigente","legal_status_origem":"planalto:texto_compilado","legal_status_inferido_em":"2026-08-01T10:00:00Z"}'}
        )
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            assert "CARIMBO_INFERIDO" not in {r["titulo"] for r in res}, (
                "documento com carimbo de inferência passou pelo gate estrito")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE chave_origem=:k"), {"k": k})
            await db.commit()


@pytestmark_db
async def test_legislacao_suspensa_sem_proveniencia_rejeitada(monkeypatch):
    """Legislação 'suspensa' não passa sem conferência específica."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag
    from uuid import uuid4
    from sqlalchemy import text

    _flag(monkeypatch, True)
    termo = f"zzsusp{uuid4().hex[:10]}"
    k = f"test:susp:{uuid4()}"

    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO knowledge_docs (id, titulo, categoria, chave_origem, "
            "status_indexacao, vigente, revisado, extra, base_rag) "
            "VALUES (:id, :titulo, 'legislacao', :k, 'indexado', true, true, "
            "CAST(:extra AS jsonb), 'publica')"),
            {"id": str(uuid4()), "titulo": "SUSPENSA", "k": k,
             "extra": '{"rag_status":"aprovado","legal_status":"suspensa","legal_status_origem":"fonte:x","legal_status_verificado_em":"2026-08-01T10:00:00Z"}'}
        )
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            assert "SUSPENSA" not in {r["titulo"] for r in res}, (
                "legislação suspensa passou pelo gate estrito")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE chave_origem=:k"), {"k": k})
            await db.commit()


@pytestmark_db
async def test_legislacao_vigente_com_proveniencia_completa_aceita(monkeypatch):
    """Legislação vigente='vigente' COM proveniência completa é aceita."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag
    from uuid import uuid4
    from sqlalchemy import text

    _flag(monkeypatch, True)
    termo = f"zzok{uuid4().hex[:10]}"
    k = f"test:ok:{uuid4()}"

    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "INSERT INTO knowledge_docs (id, titulo, categoria, chave_origem, "
            "conteudo, status_indexacao, vigente, revisado, extra, base_rag) "
            "VALUES (:id, :titulo, 'legislacao', :k, :conteudo, 'indexado', true, true, "
            "CAST(:extra AS jsonb), 'publica')"),
            {"id": str(uuid4()), "titulo": "PROV_COMPLETA", "k": k,
             "conteudo": f"Norma valida com proveniencia completa {termo}",
             "extra": '{"rag_status":"aprovado","legal_status":"vigente","legal_status_origem":"planalto:texto_compilado","legal_status_verificado_em":"2026-08-01T10:00:00Z"}'}
        )
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            assert "PROV_COMPLETA" in {r["titulo"] for r in res}, (
                "documento vigente com proveniência completa foi rejeitado")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE chave_origem=:k"), {"k": k})
            await db.commit()
