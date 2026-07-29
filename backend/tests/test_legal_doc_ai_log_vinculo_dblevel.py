"""P0 — vínculo estrutural LegalDoc ↔ AILog.

O gate não pode depender de `LEGAL_DOC_ID:<uuid>` dentro de prompt truncado.
Estes testes exigem correlação por FK + hash do conteúdo validado.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL com migrations (RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _isolar_pool_por_event_loop():
    from app.core.database import engine

    await engine.dispose(close=False)
    yield
    await engine.dispose(close=False)


async def _cenario_base(conteudo: str = "Texto jurídico " * 80):
    from app.core.database import AsyncSessionLocal
    from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
    from app.models.user import User, UserRole

    db = AsyncSessionLocal()
    user = User(
        id=str(uuid4()),
        email=f"vinculo-{uuid4()}@example.invalid",
        hashed_password="nao-utilizada",
        full_name="Usuário Fictício",
        role=UserRole.advogado,
    )
    doc = LegalDoc(
        id=str(uuid4()),
        titulo="Peça fictícia para teste",
        tipo_peca=PecaTipo.parecer,
        status=PecaStatus.rascunho,
        conteudo=conteudo,
        ai_generated=True,
        created_by=user.id,
    )
    db.add_all([user, doc])
    await db.commit()
    return db, user, doc


async def _adicionar_validacao(
    db,
    *,
    user_id: str,
    doc_id: str | None,
    content_hash: str | None,
    status_hitl,
    score: int = 90,
    criado_em: datetime | None = None,
    prompt_extra: str = "",
):
    from app.models.ai_log import AILog, AITipoUso

    log = AILog(
        id=str(uuid4()),
        user_id=user_id,
        legal_doc_id=doc_id,
        legal_doc_content_hash=content_hash,
        tipo_uso=AITipoUso.outro,
        modelo="teste/modelo",
        prompt_sanitizado=(
            f"score_confianca: {score}\n"
            "veredito: APROVAR\n"
            f"{prompt_extra}"
        ),
        resposta="RELATORIO DE VALIDACAO JURIDICA",
        status_hitl=status_hitl,
        created_at=criado_em or datetime.now(timezone.utc),
    )
    db.add(log)
    await db.commit()
    return log


async def _limpar(db, user_id: str):
    from sqlalchemy import delete
    from app.models.ai_log import AILog
    from app.models.legal_doc import LegalDoc
    from app.models.user import User

    await db.execute(delete(AILog).where(AILog.user_id == user_id))
    await db.execute(delete(LegalDoc).where(LegalDoc.created_by == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    await db.close()


@pytest.mark.asyncio
async def test_prompt_maior_que_8000_continua_recuperavel_por_vinculo():
    from app.models.ai_log import AIStatusHITL
    from app.routers.legal_docs import _conteudo_hash, _ultima_validacao_peca

    db, user, doc = await _cenario_base("A" * 30_000)
    try:
        log = await _adicionar_validacao(
            db,
            user_id=user.id,
            doc_id=doc.id,
            content_hash=_conteudo_hash(doc.conteudo),
            status_hitl=AIStatusHITL.revisado,
            prompt_extra="X" * 8_500,
        )

        resultado = await _ultima_validacao_peca(db, doc)

        assert resultado["status"] == "validada"
        assert resultado["apto_fluxo"] is True
        assert resultado["ai_log_id"] == log.id
    finally:
        await _limpar(db, user.id)


@pytest.mark.asyncio
async def test_log_legado_com_marcador_textual_nao_e_associado():
    from app.models.ai_log import AIStatusHITL
    from app.routers.legal_docs import _ultima_validacao_peca

    db, user, doc = await _cenario_base()
    try:
        await _adicionar_validacao(
            db,
            user_id=user.id,
            doc_id=None,
            content_hash=None,
            status_hitl=AIStatusHITL.revisado,
            prompt_extra=f"LEGAL_DOC_ID:{doc.id}",
        )

        resultado = await _ultima_validacao_peca(db, doc)

        assert resultado["status"] == "sem_validacao"
        assert resultado["ai_log_id"] is None
    finally:
        await _limpar(db, user.id)


@pytest.mark.asyncio
async def test_edicao_do_conteudo_invalida_validacao_anterior():
    from app.models.ai_log import AIStatusHITL
    from app.routers.legal_docs import _conteudo_hash, _ultima_validacao_peca

    db, user, doc = await _cenario_base()
    try:
        await _adicionar_validacao(
            db,
            user_id=user.id,
            doc_id=doc.id,
            content_hash=_conteudo_hash(doc.conteudo),
            status_hitl=AIStatusHITL.revisado,
        )
        assert (await _ultima_validacao_peca(db, doc))["apto_fluxo"] is True

        doc.conteudo += "\nAlteração posterior à validação."
        await db.commit()

        resultado = await _ultima_validacao_peca(db, doc)
        assert resultado["status"] == "sem_validacao"
        assert resultado["apto_fluxo"] is False
    finally:
        await _limpar(db, user.id)


@pytest.mark.asyncio
async def test_usa_a_validacao_mais_recente_da_mesma_versao():
    from app.models.ai_log import AIStatusHITL
    from app.routers.legal_docs import _conteudo_hash, _ultima_validacao_peca

    db, user, doc = await _cenario_base()
    try:
        agora = datetime.now(timezone.utc)
        await _adicionar_validacao(
            db,
            user_id=user.id,
            doc_id=doc.id,
            content_hash=_conteudo_hash(doc.conteudo),
            status_hitl=AIStatusHITL.revisado,
            score=95,
            criado_em=agora - timedelta(minutes=2),
        )
        recente = await _adicionar_validacao(
            db,
            user_id=user.id,
            doc_id=doc.id,
            content_hash=_conteudo_hash(doc.conteudo),
            status_hitl=AIStatusHITL.revisado,
            score=60,
            criado_em=agora,
        )

        resultado = await _ultima_validacao_peca(db, doc)

        assert resultado["ai_log_id"] == recente.id
        assert resultado["status"] == "score_baixo"
        assert resultado["score"] == 60
    finally:
        await _limpar(db, user.id)


@pytest.mark.asyncio
async def test_duas_pecas_do_mesmo_usuario_nao_cruzam_validacoes():
    from app.models.ai_log import AIStatusHITL
    from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
    from app.routers.legal_docs import _conteudo_hash, _validacoes_por_peca

    db, user, doc_a = await _cenario_base("Conteúdo A " * 100)
    doc_b = LegalDoc(
        id=str(uuid4()),
        titulo="Peça B",
        tipo_peca=PecaTipo.parecer,
        status=PecaStatus.rascunho,
        conteudo="Conteúdo B " * 100,
        ai_generated=True,
        created_by=user.id,
    )
    db.add(doc_b)
    await db.commit()
    try:
        log_a = await _adicionar_validacao(
            db,
            user_id=user.id,
            doc_id=doc_a.id,
            content_hash=_conteudo_hash(doc_a.conteudo),
            status_hitl=AIStatusHITL.revisado,
        )

        resultado = await _validacoes_por_peca(db, [doc_a, doc_b])

        assert resultado[doc_a.id]["ai_log_id"] == log_a.id
        assert resultado[doc_b.id]["status"] == "sem_validacao"
    finally:
        await _limpar(db, user.id)


def test_migration_123_e_reversivel_e_indexada():
    migration = (
        Path(__file__).parents[1]
        / "alembic/versions/123_legal_doc_ai_log_vinculo.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "123_legal_doc_ai_log_vinculo"' in migration
    assert 'down_revision = "122_route_usage_metrics"' in migration
    assert '"legal_doc_id"' in migration
    assert '"legal_doc_content_hash"' in migration
    assert 'ondelete="SET NULL"' in migration
    assert "create_index" in migration
    assert "drop_index" in migration
    assert "drop_column" in migration
