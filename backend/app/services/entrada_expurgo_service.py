# ── app/services/entrada_expurgo_service.py ──────────────────────────────────
# Expurgo LGPD de rascunhos abandonados da Entrada Única (Issue #647 / achado
# B6 da auditoria do PR #640).
#
# `POST /entrada/analisar` persiste os Documents originais ANTES de qualquer
# OCR/IA (deliberado — nada se perde) e guarda o rascunho da proposta em
# `DocumentIntakeBatch.resultado["entrada_unica"]`, com os fatos integrais do
# relato do cliente (pode conter dado pessoal). Quando o advogado abandona o
# rascunho — nunca clica "Criar caso" nem "Descartar" — batch e Documents
# ficam órfãos para sempre.
#
# Regra inegociável: NUNCA tocar batch com `case_id` preenchido, nem Document
# com `case_id`/`client_id` preenchido — mesmo que o batch pareça órfão (o
# Document pode ter sido vinculado por um caminho independente do batch;
# defesa em profundidade, dupla checagem no nível do Document).
#
# A checagem sozinha não basta: entre a seleção (sem lock) e o delete, uma
# conversão concorrente (POST /entrada/{id}/criar-caso) pode commitar e
# vincular exatamente o batch/Document que está sendo apagado (TOCTOU —
# achado crítico da auditoria de segurança do PR #685). Por isso, no caminho
# real (`dry_run=False`), a condição é REVALIDADA sob `SELECT ... FOR UPDATE`
# imediatamente antes de cada delete — não só na leitura inicial.
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.models.document import Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem

logger = logging.getLogger(__name__)

_STATUS_EXPURGAVEIS = ("erro", "concluido")


async def expurgar_rascunhos_entrada_unica(
    db, dias: int = 30, dry_run: bool = True
) -> dict[str, Any]:
    """Expurga (ou apenas conta, se `dry_run`) batches da Entrada Única

    Seleciona `DocumentIntakeBatch` com `case_id IS NULL` E `status IN
    ('erro', 'concluido')` E `updated_at < corte` (corte = agora - dias).

    Para cada batch qualificado, resolve os `Document`s pelos
    `DocumentIntakeItem`s do lote e confirma DE NOVO, no nível do Document,
    que `case_id IS NULL AND client_id IS NULL` antes de tocar — nunca confia
    só no filtro do batch.

    `dry_run=True` (default): só conta — não apaga nada. Relatório com
    quantos batches, quantos documentos, bytes totais e idade do rascunho
    mais antigo. `dry_run=False`: apaga o arquivo físico de cada Document
    (best-effort — `FileNotFoundError` não é fatal), depois os registros —
    `DocumentIntakeItem`, `Document` e por fim `DocumentIntakeBatch`, nessa
    ordem, todos explicitamente via ORM.

    Nunca deixa uma exceção não tratada derrubar o job — captura, loga, e
    devolve `{"erro": ...}`.
    """
    try:
        corte = datetime.now(timezone.utc) - timedelta(days=dias)

        batches = (
            (
                await db.execute(
                    select(DocumentIntakeBatch).where(
                        DocumentIntakeBatch.case_id.is_(None),
                        DocumentIntakeBatch.status.in_(_STATUS_EXPURGAVEIS),
                        (
                            (DocumentIntakeBatch.modalidade.is_(None))
                            | (DocumentIntakeBatch.modalidade != "dpt360_oportunidade")
                        ),
                        DocumentIntakeBatch.updated_at < corte,
                    )
                )
            )
            .scalars()
            .all()
        )

        batches_removidos = 0
        documentos_removidos = 0
        bytes_liberados = 0
        mais_antigo: datetime | None = None
        agora = datetime.now(timezone.utc)
        settings = get_settings()

        for batch in batches:
            atualizado_em = batch.updated_at
            if atualizado_em is not None:
                if atualizado_em.tzinfo is None:
                    atualizado_em = atualizado_em.replace(tzinfo=timezone.utc)
                if mais_antigo is None or atualizado_em < mais_antigo:
                    mais_antigo = atualizado_em

            itens = (
                (
                    await db.execute(
                        select(DocumentIntakeItem).where(
                            DocumentIntakeItem.batch_id == batch.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            documentos_do_batch: list[Document] = []
            for item in itens:
                doc = await db.get(Document, item.document_id)
                if doc is None:
                    continue
                # Defesa em profundidade (regra inegociável da issue): mesmo
                # que o batch esteja "órfão", o Document pode ter sido
                # vinculado a um caso/cliente por caminho independente do
                # batch — NUNCA remove Document com case_id/client_id.
                if doc.case_id is not None or doc.client_id is not None:
                    logger.warning(
                        "[entrada_expurgo] batch %s órfão mas Document %s tem "
                        "case_id/client_id preenchido — Document preservado, "
                        "batch pulado nesta execução",
                        batch.id, doc.id,
                    )
                    documentos_do_batch = None
                    break
                documentos_do_batch.append(doc)

            if documentos_do_batch is None:
                continue

            if dry_run:
                batches_removidos += 1
                documentos_removidos += len(documentos_do_batch)
                bytes_liberados += sum(
                    (d.size_bytes or 0) for d in documentos_do_batch
                )
                continue

            # Revalidação sob lock — fecha a janela TOCTOU entre a seleção
            # acima (sem lock) e o delete abaixo: uma conversão concorrente
            # (POST /entrada/{id}/criar-caso, que grava case_id sob
            # with_for_update em entrada_service.py) pode commitar bem no
            # meio dessa função. Sem revalidar SOB LOCK imediatamente antes
            # de apagar, o expurgo apagaria documento e batch já vinculados
            # a um caso recém-criado com sucesso — achado crítico da
            # auditoria de segurança do PR #685. O SELECT ... FOR UPDATE
            # aqui bloqueia até a transação concorrente (que faz UPDATE nessa
            # mesma linha) commitar ou desfazer, e então relê o valor
            # JÁ COMMITADO — não o snapshot de antes.
            # populate_existing=True é obrigatório aqui (mesmo padrão de
            # criar_caso_do_rascunho): sem ele, o SQLAlchemy acha o objeto
            # já carregado no identity map desta Session (pela seleção sem
            # lock, mais acima) e devolve os atributos ANTIGOS em memória —
            # mesmo com o lock corretamente adquirido e a linha do banco já
            # atualizada. O lock sozinho não basta; precisa forçar o reload.
            batch_travado = (
                await db.execute(
                    select(DocumentIntakeBatch)
                    .where(DocumentIntakeBatch.id == batch.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if batch_travado is None or batch_travado.case_id is not None:
                logger.warning(
                    "[entrada_expurgo] batch %s convertido/removido entre a "
                    "seleção e o expurgo — pulado nesta execução", batch.id,
                )
                continue

            documentos_travados: list[Document] = []
            pular_batch = False
            for doc in documentos_do_batch:
                doc_travado = (
                    await db.execute(
                        select(Document)
                        .where(Document.id == doc.id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).scalar_one_or_none()
                if (
                    doc_travado is None
                    or doc_travado.case_id is not None
                    or doc_travado.client_id is not None
                ):
                    logger.warning(
                        "[entrada_expurgo] Document %s vinculado entre a "
                        "seleção e o expurgo (batch %s) — batch pulado "
                        "nesta execução", doc.id, batch.id,
                    )
                    pular_batch = True
                    break
                documentos_travados.append(doc_travado)
            if pular_batch:
                continue

            # Ordem: Items → Documents → Batch, todos apagados EXPLICITAMENTE
            # pelo ORM nesta função — não depende de cascade implícita (FK
            # ondelete="CASCADE" existe em produção, mas a suíte de testes
            # roda em aiosqlite sem PRAGMA foreign_keys=ON; o relationship
            # `items` também tem cascade="all, delete-orphan", mas cascatear
            # via lazy-load do ORM dentro de uma AsyncSession é uma
            # dependência frágil demais para uma rotina de expurgo
            # irreversível). Deletar o Item antes evita erro de "already
            # deleted" quando o batch for removido em seguida.
            for item in itens:
                await db.delete(item)

            upload_root = os.path.realpath(settings.UPLOAD_DIR)
            for doc in documentos_travados:
                # Contido em UPLOAD_DIR: defesa em profundidade contra um
                # filepath corrompido/absoluto (o campo é sempre gerado pelo
                # servidor hoje, mas o job roda sem revisão humana — não
                # confiar cegamente em dado de banco antes de os.remove()).
                full_path = os.path.realpath(
                    os.path.join(settings.UPLOAD_DIR, doc.filepath or "")
                )
                if not full_path.startswith(upload_root + os.sep):
                    logger.warning(
                        "[entrada_expurgo] filepath fora de UPLOAD_DIR para "
                        "Document %s — registro removido, arquivo físico "
                        "NÃO tocado", doc.id,
                    )
                else:
                    try:
                        os.remove(full_path)
                    except FileNotFoundError:
                        pass  # já removido antes (não-fatal)
                    except OSError as exc:
                        logger.warning(
                            "[entrada_expurgo] falha ao remover arquivo "
                            "físico de %s (%s) — registro será removido do "
                            "banco mesmo assim",
                            doc.id, exc,
                        )
                bytes_liberados += doc.size_bytes or 0
                await db.delete(doc)
                documentos_removidos += 1

            await db.delete(batch_travado)
            batches_removidos += 1

        if not dry_run and (batches_removidos or documentos_removidos):
            await db.commit()

        resultado = {
            "dry_run": dry_run,
            "batches_removidos": batches_removidos,
            "documentos_removidos": documentos_removidos,
            "bytes_liberados": bytes_liberados,
            "mais_antigo_dias": (
                (agora - mais_antigo).days if mais_antigo is not None else None
            ),
            "corte": corte.isoformat(),
        }
        if not dry_run and (batches_removidos or documentos_removidos):
            logger.info(
                "[entrada_expurgo] %d batch(es) e %d documento(s) expurgados "
                "(%d bytes liberados)",
                batches_removidos, documentos_removidos, bytes_liberados,
            )
        return resultado
    except Exception as exc:  # nunca derruba o job (padrão route_usage.expurgar_antigos)
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning("[entrada_expurgo] falha (%s)", type(exc).__name__)
        return {"erro": type(exc).__name__}
