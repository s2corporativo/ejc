"""Contratos P0.1 do gate estrito de vigência normativa.

Uma string `legal_status='vigente'` não basta para fundamentação atual: o estado
precisa ter proveniência e carimbo de verificação positivos. Os testes DB-level
inserem documento + chunk pesquisável para provar o comportamento real do RAG,
sem depender apenas de inspeção textual do SQL.
"""
from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

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


def test_gate_estrito_exige_status_canonico_com_proveniencia_positiva():
    filtro = _FILTRO_VIGENCIA_VERIFICADA_RAG

    assert "legal_status" in filtro
    assert "legal_status_origem" in filtro
    assert "legal_status_verificado_em" in filtro
    assert "legal_status_inferido_em" in filtro
    assert "'vigente'" in filtro
    # Aliases legados podem continuar no bloqueio de revogadas, mas NÃO podem
    # provar vigência positiva de direito atual no modo estrito.
    assert "situacao_normativa" not in filtro
    assert "vigencia_status" not in filtro


def test_status_inferido_nao_e_equivalente_a_verificado():
    filtro = _FILTRO_VIGENCIA_VERIFICADA_RAG
    assert "legal_status_inferido_em" in filtro
    assert "legal_status_verificado_em" in filtro


def test_suspensa_e_parcialmente_revogada_nao_passam_como_vigencia_atual():
    filtro = _FILTRO_VIGENCIA_VERIFICADA_RAG
    trecho_positivo = filtro.split("'vigente'", 1)[1]
    assert "'suspensa'" not in trecho_positivo
    assert "'parcialmente_revogada'" not in trecho_positivo


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
# Testes DB-level: documento + chunk real, busca textual determinística
# ══════════════════════════════════════════════════════════════════════════

pytestmark_db = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="Teste de banco (RUN_DB_TESTS=1 para rodar)",
)


@pytest.fixture
async def rag_textual(monkeypatch):
    """Força o fallback ILIKE e descarta o pool no mesmo event loop do teste."""
    from app.services import embedding_service

    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)
    yield

    from app.core.database import engine
    await engine.dispose()


async def _ins_doc_chunk(db, *, titulo: str, termo: str, extra: dict) -> str:
    """Insere um documento legislativo aprovado e um chunk pesquisável."""
    doc_id = str(uuid4())
    chave = f"test:p01:prov:{uuid4()}"
    await db.execute(
        text(
            "INSERT INTO knowledge_docs "
            "(id, titulo, categoria, chave_origem, status_indexacao, vigente, "
            "revisado, extra) "
            "VALUES (:id, :titulo, 'legislacao', :chave, 'indexado', true, "
            "true, CAST(:extra AS jsonb))"
        ),
        {
            "id": doc_id,
            "titulo": titulo,
            "chave": chave,
            "extra": json.dumps({"rag_status": "aprovado", **extra}),
        },
    )
    await db.execute(
        text(
            "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
            "VALUES (:id, :doc_id, 0, :conteudo)"
        ),
        {
            "id": str(uuid4()),
            "doc_id": doc_id,
            "conteudo": f"Conteúdo legislativo de teste {termo}",
        },
    )
    return doc_id


async def _buscar_titulos(db, termo: str) -> set[str]:
    from app.services.ai_service import buscar_contexto_rag

    resultados = await buscar_contexto_rag(
        db, termo, limite=20, modo_or=True,
    )
    return {r["titulo"] for r in resultados}


async def _apagar_doc(db, doc_id: str) -> None:
    # FK dos chunks usa ON DELETE CASCADE.
    await db.execute(text("DELETE FROM knowledge_docs WHERE id=:id"), {"id": doc_id})
    await db.commit()


@pytestmark_db
@pytest.mark.parametrize(
    ("rotulo", "extra"),
    [
        (
            "SEM_PROVENIENCIA",
            {"legal_status": "vigente"},
        ),
        (
            "SEM_DATA_VERIFICACAO",
            {
                "legal_status": "vigente",
                "legal_status_origem": "planalto:texto_compilado",
            },
        ),
        (
            "STATUS_INFERIDO",
            {
                "legal_status": "vigente",
                "legal_status_origem": "planalto:texto_compilado",
                "legal_status_verificado_em": "2026-08-01T10:00:00Z",
                "legal_status_inferido_em": "2026-08-01T10:00:00Z",
            },
        ),
        (
            "SUSPENSA",
            {
                "legal_status": "suspensa",
                "legal_status_origem": "fonte:oficial",
                "legal_status_verificado_em": "2026-08-01T10:00:00Z",
            },
        ),
        (
            "PARCIALMENTE_REVOGADA",
            {
                "legal_status": "parcialmente_revogada",
                "legal_status_origem": "fonte:oficial",
                "legal_status_verificado_em": "2026-08-01T10:00:00Z",
            },
        ),
        (
            "ALIAS_LEGADO",
            {
                "situacao_normativa": "vigente",
                "legal_status_origem": "legado:fonte",
                "legal_status_verificado_em": "2026-08-01T10:00:00Z",
            },
        ),
    ],
)
async def test_gate_estrito_rejeita_estados_sem_prova_canonica(
    monkeypatch, rag_textual, rotulo, extra,
):
    from app.core.database import AsyncSessionLocal

    _flag(monkeypatch, True)
    termo = f"zzp01neg{uuid4().hex[:12]}"
    titulo = f"P01_{rotulo}_{uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db:
        doc_id = await _ins_doc_chunk(db, titulo=titulo, termo=termo, extra=extra)
        await db.commit()
        try:
            titulos = await _buscar_titulos(db, termo)
            assert titulo not in titulos, (
                f"{rotulo} passou pelo gate estrito sem prova canônica suficiente"
            )
        finally:
            await _apagar_doc(db, doc_id)


@pytestmark_db
async def test_legislacao_vigente_com_proveniencia_completa_e_aceita(
    monkeypatch, rag_textual,
):
    from app.core.database import AsyncSessionLocal

    _flag(monkeypatch, True)
    termo = f"zzp01ok{uuid4().hex[:12]}"
    titulo = f"P01_PROV_COMPLETA_{uuid4().hex[:8]}"
    extra = {
        "legal_status": "vigente",
        "legal_status_origem": "planalto:texto_compilado",
        "legal_status_verificado_em": "2026-08-01T10:00:00Z",
    }

    async with AsyncSessionLocal() as db:
        doc_id = await _ins_doc_chunk(db, titulo=titulo, termo=termo, extra=extra)
        await db.commit()
        try:
            titulos = await _buscar_titulos(db, termo)
            assert titulo in titulos, (
                "legislação vigente com proveniência positiva completa foi rejeitada"
            )
        finally:
            await _apagar_doc(db, doc_id)
