# -*- coding: utf-8 -*-
"""Integração real (dblevel) do rescan SHA-256 — Épico #1019 A3.2.

Cobertura: seleção de vigentes contra o banco real (migration 142), gravação
de batch/itens pelo próprio serviço, divergência de tamanho
(tamanho_divergente), arquivo ausente (nao_disponivel) e divergência contra
o último intake (diverge_do_intake). LGPD: filepath nunca aparece em
divergências.

Padrão dos demais *_dblevel.py: handler direto com ``AsyncSessionLocal``.
Sem RUN_DB_TESTS=1, pulam.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.models import DocumentHashRescanBatch, DocumentHashRescanItem
from app.services import document_rescan_service as servico

# Mesmo padrão dos demais *_dblevel.py: `pytestmark` marca o módulo inteiro como
# skip. `pytest.skip()` em nível de módulo (sem allow_module_level) NÃO pula o
# arquivo — levanta erro de COLETA e interrompe a suíte inteira quando não há
# Postgres, deixando zero testes executados.
pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_selecao_exclui_soft_deleted_e_itens_sao_gravados_dblevel():
    """Vigentes selecionados via banco; itens gravados; lote conclui."""
    from app.core.database import AsyncSessionLocal

    cliente = _id("cli")
    doc = _id("doc")

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO clients (id, tipo, nome)
            VALUES (:id, 'PF', :nome)
            ON CONFLICT (id) DO NOTHING
        """), {"id": cliente, "nome": "Cliente Teste Rescan"})
        await db.execute(text("""
            INSERT INTO documents (id, titulo, filename, filepath, client_id,
                                   confidencialidade, deleted_at)
            VALUES (:id, :titulo, :filename, :filepath, :cliente, 'normal', NULL),
                   (:id2, :titulo2, :filename2, :filepath2, :cliente, 'normal', now())
            ON CONFLICT (id) DO NOTHING
        """), {"id": doc, "titulo": "Rescan", "filename": "rescan.pdf",
               "filepath": "2026/08/rescan.pdf", "cliente": cliente,
               "id2": doc + "-x", "titulo2": "Removido", "filename2": "removido.pdf",
               "filepath2": "2026/08/removido.pdf"})
        await db.commit()

    async with AsyncSessionLocal() as db:
        vigentes = await servico.selecionar_documentos(db, client_id=cliente)
        assert len(vigentes) == 1, "soft-deleted não deve ser selecionado"
        assert vigentes[0].id == doc

        batch = DocumentHashRescanBatch(
            id=_id("batch"), cliente_id=cliente, caso_id=None,
            document_ids_json=None, criado_por=None, status="pendente",
            total_selecionado=len(vigentes),
        )
        db.add(batch)
        await db.commit()

        resultado = await servico.executar_rescan(
            upload_root="/tmp/uploads-inexistente-rescan",
            rclone_config=None,
            documentos=vigentes,
            db=db,
        )
        assert resultado.itens_nao_disponiveis >= 1, "arquivo ausente"
        assert not any(
            "/tmp/uploads" in d.get("motivo", "")
            for d in resultado.divergencias
        ), "/filepath jamais em mensagens"
        # Conclusão do batch é responsabilidade do dispatcher
        # (``app.tasks.rescan_tasks._concluir_batch``), não do serviço.
        await db.execute(
            text("UPDATE document_hash_rescan_batches SET status = 'concluido'"
                 " WHERE id = :bid"),
            {"bid": batch.id},
        )
        await db.commit()

    # itens persistiram na transação do serviço (flush+commit do serviço)
    async with AsyncSessionLocal() as db:
        items = (await db.execute(select(DocumentHashRescanItem))).scalars().all()
        assert items, "itens gravados"
        assert any(i.status == "nao_disponivel" for i in items)
        batch_f = (await db.execute(select(DocumentHashRescanBatch)
                                    .where(DocumentHashRescanBatch.id == batch.id)
                                    )).scalar_one()
        assert batch_f.status == "concluido", "conclusão do batch gravada"


@pytest.mark.asyncio
async def test_diverge_do_intake_registra_motivos_dblevel():
    """Hash/tamanho divergentes do último intake viram motivo rastreável."""
    from app.core.database import AsyncSessionLocal

    cliente = _id("cli")
    doc = _id("doc")
    doc2 = _id("doc")

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO clients (id, tipo, nome)
            VALUES (:id, 'PF', :nome)
            ON CONFLICT (id) DO NOTHING
        """), {"id": cliente, "nome": "Cliente Teste Rescan 2"})
        await db.execute(text("""
            INSERT INTO documents (id, titulo, filename, filepath, size_bytes,
                                   client_id, confidencialidade, deleted_at)
            VALUES (:id, :titulo, :filename, :filepath, :size, :cliente,
                    'normal', NULL),
                   (:id2, :titulo2, :filename2, :filepath2, :size2, :cliente,
                    'normal', NULL)
            ON CONFLICT (id) DO NOTHING
        """), {"id": doc, "titulo": "Intake", "filename": "intake.pdf",
               "filepath": "2026/08/intake.pdf", "size": 7, "cliente": cliente,
               "id2": doc2, "titulo2": "Ausente", "filename2": "ausente.pdf",
               "filepath2": "2026/08/ausente.pdf", "size2": 3})
        ib = _id("ib")
        await db.execute(text("""
            INSERT INTO document_intake_batches
                (id, client_id, modalidade, status, document_count,
                 total_bytes, created_by)
            VALUES (:ib, :cliente, 'local', 'concluido', 1, :size, :cliente)
            ON CONFLICT (id) DO NOTHING
        """), {"ib": ib, "cliente": cliente, "size": 7})
        await db.execute(text("""
            INSERT INTO document_intake_items
                (id, batch_id, document_id, filename, original_filename,
                 extension, size_bytes, sha256)
            VALUES (:int, :ib, :doc, :filename, :filename, 'pdf', :size, :sha)
            ON CONFLICT (id) DO NOTHING
        """), {"int": _id("int"), "ib": ib, "doc": doc,
               "filename": "intake.pdf", "size": 3, "sha": "a" * 64})
        await db.commit()

    # Arquivo real presente no disco com TAMANHO DIVERGENTE do metadado
    # documental (7 bytes) — a primitiva reporta tamanho_divergente;
    # ``ausente.pdf`` não existe — a primitiva reporta nao_disponivel.
    tmp = Path("/tmp/ejc-rescan-intake-dblevel/2026/08")
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "intake.pdf").write_bytes(b"xyz")  # 3 bytes ≠ 7
    (tmp / "ausente.pdf").unlink(missing_ok=True)

    async with AsyncSessionLocal() as db:
        vigentes = await servico.selecionar_documentos(
            db, document_ids=[doc, doc2],
        )
        resultado = await servico.executar_rescan(
            upload_root="/tmp/ejc-rescan-intake-dblevel",
            rclone_config=None, documentos=vigentes, db=db)
        motivos = {d["motivo"] for d in resultado.divergencias}
        assert "tamanho_divergente" in motivos, motivos
        status = {d["status"] for d in resultado.divergencias}
        assert "nao_disponivel" in status, status
