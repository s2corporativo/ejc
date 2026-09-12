"""DB-level: fechamento de caso + memória institucional (#1466).

Prova no handler real `encerrar_caso` que:
- o precedente interno fica escopado ao cliente/caso corretos;
- falha de embeddings/RAG é revertida no SAVEPOINT e não vira 500;
- o encerramento e seu AuditLog continuam persistidos;
- nenhum KnowledgeDoc parcial/global fica para trás.

Requer PostgreSQL com migrations, como os demais testes ``*_dblevel.py``.
"""
from __future__ import annotations

import logging
import os
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy import select, text
from starlette.background import BackgroundTasks

from app.routers.cases import EncerrarCasoReq

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


def _req() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/cases/encerrar",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 50000),
    })


async def _criar_user(db) -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'RAG Teste', 'socio', true)"
        ),
        {"id": uid, "email": f"rag-{uid[:8]}@teste.local"},
    )
    return uid


async def _criar_cliente(db) -> str:
    cid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO clients (id, tipo, nome, email, status) "
            "VALUES (:id, 'PF', :nome, :email, 'ativo')"
        ),
        {
            "id": cid,
            "nome": f"Cliente RAG {cid[:8]}",
            "email": f"{cid[:8]}@teste.local",
        },
    )
    return cid


async def _criar_caso(db, client_id: str, user_id: str) -> str:
    case_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO cases (id, numero_interno, titulo, area, status, client_id, "
            "advogado_responsavel_id, proxima_acao) VALUES "
            "(:id, :numero, :titulo, 'civil', 'em_producao', :cid, :uid, 'Revisar encerramento')"
        ),
        {
            "id": case_id,
            "numero": f"DPT-2099-{uuid4().hex[:8]}",
            "titulo": f"Caso RAG {case_id[:8]}",
            "cid": client_id,
            "uid": user_id,
        },
    )
    return case_id


async def _carregar_user(db, user_id: str):
    from app.models.user import User

    return (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one()


async def _limpar(db, *, case_id: str, user_id: str, client_id: str) -> None:
    await db.execute(
        text(
            "DELETE FROM knowledge_chunks WHERE doc_id IN "
            "(SELECT id FROM knowledge_docs WHERE case_id = :case_id)"
        ),
        {"case_id": case_id},
    )
    await db.execute(
        text("DELETE FROM knowledge_docs WHERE case_id = :case_id"),
        {"case_id": case_id},
    )
    await db.execute(
        text("DELETE FROM case_movimentos WHERE case_id = :case_id"),
        {"case_id": case_id},
    )
    await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": case_id})

    # audit_logs é WORM; o GUC existe exclusivamente para expurgo controlado.
    await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
    await db.execute(
        text("DELETE FROM audit_logs WHERE user_id = :uid"),
        {"uid": user_id},
    )
    await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


def _payload() -> EncerrarCasoReq:
    return EncerrarCasoReq(
        resultado="acordo",
        motivo_resultado="Acordo homologado após composição entre as partes",
        provas_determinantes="Documentos contratuais e prova documental convergente",
        licoes_aprendidas="Validar os documentos essenciais antes da negociação final",
        alimentar_rag=True,
        confirmar_alertas=True,
        sincronizar_processo_eletronico=False,
    )


async def _dossie_ficticio(*args, **kwargs):
    del args, kwargs
    return {
        "texto": (
            "Contexto jurídico sintético e sanitizado para teste de precedente interno. "
            "Nenhum dado pessoal real integra esta massa de homologação."
        )
    }


@pytest.mark.asyncio
async def test_encerrar_alimenta_rag_com_escopo_exato(monkeypatch):
    from app.core.database import AsyncSessionLocal
    from app.models.rag import BaseRag, KnowledgeDoc
    from app.routers.cases import encerrar_caso
    from app.services import ai_core_hardening_patch, ingestion_service
    from app.services import case_context

    async def sem_embeddings(textos):
        assert textos
        return None

    monkeypatch.setattr(case_context, "montar_dossie", _dossie_ficticio)
    monkeypatch.setattr(ingestion_service, "gerar_embeddings", sem_embeddings)
    ai_core_hardening_patch._instalar_resolucao_escopo_rag()

    async with AsyncSessionLocal() as db:
        user_id = await _criar_user(db)
        client_id = await _criar_cliente(db)
        case_id = await _criar_caso(db, client_id, user_id)
        await db.commit()
        try:
            user = await _carregar_user(db, user_id)
            resposta = await encerrar_caso(
                case_id,
                _payload(),
                BackgroundTasks(),
                _req(),
                db=db,
                cu=user,
            )

            assert "Caso encerrado" in resposta["detail"]

            row = (
                await db.execute(
                    text("SELECT status FROM cases WHERE id = :id"),
                    {"id": case_id},
                )
            ).scalar_one()
            assert row == "encerrado"

            doc = (
                await db.execute(
                    select(KnowledgeDoc).where(
                        KnowledgeDoc.chave_origem == f"caso:{case_id}",
                        KnowledgeDoc.vigente.is_(True),
                    )
                )
            ).scalar_one()
            assert doc.client_id == client_id
            assert doc.case_id == case_id
            assert doc.base_rag == BaseRag.caso

            globais = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM knowledge_docs "
                        "WHERE chave_origem = :chave AND client_id IS NULL"
                    ),
                    {"chave": f"caso:{case_id}"},
                )
            ).scalar_one()
            assert globais == 0
        finally:
            await _limpar(
                db,
                case_id=case_id,
                user_id=user_id,
                client_id=client_id,
            )


@pytest.mark.asyncio
async def test_falha_rag_nao_desfaz_encerramento_nem_auditoria(monkeypatch, caplog):
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import encerrar_caso
    from app.services import ai_core_hardening_patch, ingestion_service
    from app.services import case_context

    marcador_sensivel = "CONTEUDO-SENSIVEL-NAO-DEVE-VAZAR"

    async def embeddings_indisponiveis(textos):
        assert textos
        raise RuntimeError(marcador_sensivel)

    monkeypatch.setattr(case_context, "montar_dossie", _dossie_ficticio)
    monkeypatch.setattr(ingestion_service, "gerar_embeddings", embeddings_indisponiveis)
    ai_core_hardening_patch._instalar_resolucao_escopo_rag()

    async with AsyncSessionLocal() as db:
        user_id = await _criar_user(db)
        client_id = await _criar_cliente(db)
        case_id = await _criar_caso(db, client_id, user_id)
        await db.commit()
        try:
            user = await _carregar_user(db, user_id)

            with caplog.at_level(logging.WARNING, logger="ejc.ai.core.hardening"):
                resposta = await encerrar_caso(
                    case_id,
                    _payload(),
                    BackgroundTasks(),
                    _req(),
                    db=db,
                    cu=user,
                )

            assert "Caso encerrado" in resposta["detail"]
            assert marcador_sensivel not in caplog.text
            assert "RuntimeError" in caplog.text

            status = (
                await db.execute(
                    text("SELECT status FROM cases WHERE id = :id"),
                    {"id": case_id},
                )
            ).scalar_one()
            assert status == "encerrado"

            docs = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM knowledge_docs "
                        "WHERE chave_origem = :chave"
                    ),
                    {"chave": f"caso:{case_id}"},
                )
            ).scalar_one()
            assert docs == 0

            audit = (
                await db.execute(
                    text(
                        "SELECT acao, entidade, registro_id, detalhes "
                        "FROM audit_logs WHERE user_id = :uid "
                        "AND entidade = 'cases' AND registro_id = :rid "
                        "AND acao = 'UPDATE' ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"uid": user_id, "rid": case_id},
                )
            ).one()
            assert audit[0] == "UPDATE"
            assert audit[1] == "cases"
            assert audit[2] == case_id
            assert marcador_sensivel not in (audit[3] or "")
        finally:
            await _limpar(
                db,
                case_id=case_id,
                user_id=user_id,
                client_id=client_id,
            )
