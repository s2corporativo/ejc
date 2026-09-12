"""Regressão do achado CRÍTICO da auditoria de segurança do PR #685 (Issue #647).

`expurgar_rascunhos_entrada_unica` selecionava batch/Document candidatos SEM
lock, e só verificava `case_id`/`client_id` uma vez, antes do delete. Isso
abria uma janela TOCTOU: se `POST /entrada/{id}/criar-caso` (que grava
`case_id` sob `with_for_update()`, em `entrada_service.py`) commitasse
EXATAMENTE nessa janela, o expurgo apagava documento e batch já vinculados a
um caso recém-criado com sucesso — hard delete irreversível de dado em uso.

A correção revalida a condição sob `SELECT ... FOR UPDATE` imediatamente
antes de cada delete (não só na leitura inicial): o lock força o expurgo a
esperar a conversão concorrente terminar e reler o valor JÁ COMMITADO.

Esse cenário só é reproduzível com locking real de Postgres — a suíte padrão
roda em aiosqlite de conexão única, que não simula duas transações
concorrentes disputando `FOR UPDATE`. Por isso este teste exige
RUN_DB_TESTS=1 (mesmo padrão dos demais *_dblevel.py) e usa DUAS
`AsyncSession`s distintas, deliberadamente interladas com `asyncio.sleep`
para forçar a corrida a acontecer sempre, não só ocasionalmente.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.document import Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem
from app.services.entrada_expurgo_service import expurgar_rascunhos_entrada_unica

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com locking real (defina RUN_DB_TESTS=1)",
)


async def _semear_rascunho_expirado(db) -> tuple[str, str, str, str]:
    """User + Client + batch órfão expirado (elegível ao expurgo) + Document
    órfão + Item, exatamente como um rascunho abandonado há 31+ dias."""
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, "
             "is_active) VALUES (:id, :email, 'x', 'Advogado Corrida', "
             "'advogado', true)"),
        {"id": uid, "email": f"corrida-{uid[:8]}@teste.local"},
    )
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', 'Cliente Corrida', :email, 'ativo')"),
        {"id": cid, "email": f"cliente-corrida-{cid[:8]}@teste.local"},
    )

    doc_id = str(uuid4())
    db.add(Document(
        id=doc_id, titulo="Comprovante — corrida", filename="c.pdf",
        filepath=f"2026/01/{doc_id}.pdf", case_id=None, client_id=None,
    ))

    batch_id = str(uuid4())
    antigo = datetime.now(timezone.utc) - timedelta(days=40)
    db.add(DocumentIntakeBatch(
        id=batch_id, status="concluido", created_by=uid,
        document_count=1, resultado={"entrada_unica": {"rascunho_id": batch_id}},
    ))
    await db.flush()
    # updated_at tem onupdate=func.now() no model — força a data antiga via
    # UPDATE direto, do mesmo jeito que os outros *_dblevel.py fazem quando
    # precisam simular idade sem esperar o relógio real.
    await db.execute(
        text("UPDATE document_intake_batches SET updated_at=:d WHERE id=:id"),
        {"d": antigo, "id": batch_id},
    )

    db.add(DocumentIntakeItem(
        id=str(uuid4()), batch_id=batch_id, document_id=doc_id,
        filename="c.pdf", original_filename="c.pdf", extension=".pdf",
        size_bytes=10, sha256="0" * 64,
    ))
    await db.commit()
    return uid, cid, batch_id, doc_id


async def test_conversao_concorrente_vence_a_corrida_documento_sobrevive():
    """Reproduz a corrida: task A converte o rascunho em caso (lock +
    UPDATE + sleep + commit) enquanto task B roda o expurgo concorrentemente.
    Documento e batch precisam sobreviver — vinculados ao caso, intocados."""
    async with AsyncSessionLocal() as db_setup:
        uid, cid, batch_id, doc_id = await _semear_rascunho_expirado(db_setup)

    resultado_expurgo: dict = {}

    async def _tarefa_conversao():
        async with AsyncSessionLocal() as db_a:
            # Mesmo padrão de criar_caso_do_rascunho: lock pessimista do
            # batch antes de qualquer escrita.
            batch = (await db_a.execute(
                select(DocumentIntakeBatch)
                .where(DocumentIntakeBatch.id == batch_id)
                .with_for_update()
            )).scalar_one()

            case_id = str(uuid4())
            await db_a.execute(
                text("INSERT INTO cases (id, titulo, area, status, client_id, "
                     "advogado_responsavel_id) VALUES "
                     "(:id, 'Caso da corrida', 'civil', 'aberto', :cid, :resp)"),
                {"id": case_id, "cid": cid, "resp": uid},
            )

            doc = (await db_a.execute(
                select(Document).where(Document.id == doc_id)
            )).scalar_one()
            doc.case_id = case_id
            doc.client_id = cid
            batch.case_id = case_id

            # Janela deliberadamente alargada: dá tempo da task B (expurgo)
            # selecionar os candidatos ANTES deste commit e tentar travar
            # DEPOIS que a UPDATE acima já tomou o lock de linha — é
            # exatamente a ordem que reproduz o TOCTOU original.
            await asyncio.sleep(0.6)
            await db_a.commit()
            return case_id

    async def _tarefa_expurgo():
        async with AsyncSessionLocal() as db_b:
            # Pequeno atraso para garantir que a task A já tomou o lock do
            # batch (via with_for_update) antes do expurgo tentar o dele.
            await asyncio.sleep(0.1)
            resultado_expurgo.update(
                await expurgar_rascunhos_entrada_unica(db_b, dias=30, dry_run=False)
            )

    case_id_criado, _ = await asyncio.gather(_tarefa_conversao(), _tarefa_expurgo())

    # Enquanto retenção/legal hold não forem verificáveis, a barreira P0
    # antecede inclusive a antiga corrida TOCTOU. O scheduler trata esse estado
    # como erro operacional de propósito: job habilitado não pode reportar "ok"
    # quando a exclusão irreversível está bloqueada.
    assert resultado_expurgo["bloqueado"] is True, resultado_expurgo
    assert resultado_expurgo["erro"] == "retencao_legal_hold_nao_codificados"
    assert resultado_expurgo["motivo"] == "retencao_legal_hold_nao_codificados"
    # A propriedade de segurança original permanece: a corrida nunca pode
    # apagar batch/documento que está sendo convertido em caso.
    assert resultado_expurgo["batches_removidos"] == 0, (
        "expurgo removeu batch vinculado a caso recém-criado — corrida não fechada"
    )
    assert resultado_expurgo["documentos_removidos"] == 0

    async with AsyncSessionLocal() as db_check:
        doc_sobrevivente = (await db_check.execute(
            select(Document).where(Document.id == doc_id)
        )).scalar_one_or_none()
        batch_sobrevivente = (await db_check.execute(
            select(DocumentIntakeBatch).where(DocumentIntakeBatch.id == batch_id)
        )).scalar_one_or_none()

    assert doc_sobrevivente is not None, "Document foi apagado pelo expurgo — corrida não fechada"
    assert doc_sobrevivente.case_id == case_id_criado
    assert doc_sobrevivente.client_id is not None
    assert batch_sobrevivente is not None, "Batch foi apagado pelo expurgo — corrida não fechada"
    assert batch_sobrevivente.case_id == case_id_criado
