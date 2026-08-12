"""Ciclo de vida e retenção LGPD de oportunidades DPT360 (Issue #1086).

Máquina de estados canônica com 7 estados (triagem_pendente → triagem_concluida → descartada/expirada → anonimizada → expurgada).
Anonimização automática via job (remove email/telefone/mensagem/contato após 30 dias de descarte).
Expurgo automático via job (deleta records anonimizados após 30 dias).
Proteção TOCTOU via SELECT...FOR UPDATE com populate_existing=True.
Auditoria WORM sem PII (apenas metadados de transição).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select, update

from app.core.config import get_settings
from app.models.audit_log import criar_audit_log
from app.models.document import Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem

logger = logging.getLogger(__name__)

# Estados canônicos
ESTADO_TRIAGEM_PENDENTE = "triagem_pendente"
ESTADO_TRIAGEM_CONCLUIDA = "triagem_concluida"
ESTADO_CONVERTIDA = "convertida"
ESTADO_DESCARTADA = "descartada"
ESTADO_EXPIRADA = "expirada"
ESTADO_ANONIMIZADA = "anonimizada"
ESTADO_EXPURGADA = "expurgada"

# Transições válidas (manuais, via rota)
TRANSICOES_VALIDAS = {
    ESTADO_TRIAGEM_PENDENTE: [ESTADO_TRIAGEM_CONCLUIDA, ESTADO_DESCARTADA],
    ESTADO_TRIAGEM_CONCLUIDA: [ESTADO_TRIAGEM_PENDENTE, ESTADO_DESCARTADA],
    ESTADO_DESCARTADA: [],  # Só job de anonimização pode mover
    ESTADO_EXPIRADA: [],  # Só job de anonimização pode mover
    ESTADO_ANONIMIZADA: [],  # Só job de expurgo pode mover
    ESTADO_CONVERTIDA: [],  # Nunca muda após conversão
}

# Prazos de retenção (dias)
PRAZO_TRIAGEM_PENDENTE = 30  # Até análise ou expiração
PRAZO_TRIAGEM_CONCLUIDA = 90  # Após análise
PRAZO_DESCARTADA = 30  # Antes de anonimizar
PRAZO_ANONIMIZADA = 30  # Antes de expurgar


async def mudar_estado(
    db,
    user_id: str,
    user_role: str | None,
    batch_id: str,
    novo_estado: str,
    motivo: str | None = None,
) -> dict[str, Any]:
    """Muda estado de oportunidade com validação e TOCTOU protection.

    Apenas staff (`gestao`/`admin`) pode mudar estado manualmente.
    Transições são validadas via TRANSICOES_VALIDAS.

    Sob SELECT...FOR UPDATE, revalida:
    - estado atual é legal para transição
    - batch não foi convertida (case_id não foi preenchido concorrentemente)

    Registra auditoria sem PII da oportunidade.
    """
    try:
        batch_travado = (
            await db.execute(
                select(DocumentIntakeBatch)
                .where(DocumentIntakeBatch.id == batch_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

        if batch_travado is None:
            return {"erro": "batch_nao_encontrado", "batch_id": batch_id}

        if batch_travado.modalidade != "dpt360_oportunidade":
            return {
                "erro": "nao_e_oportunidade_dpt360",
                "batch_id": batch_id,
                "modalidade": batch_travado.modalidade,
            }

        estado_atual = batch_travado.ciclo_vida_estado or ESTADO_TRIAGEM_PENDENTE

        if (
            estado_atual == ESTADO_CONVERTIDA
            or batch_travado.case_id is not None
        ):
            return {
                "erro": "oportunidade_ja_convertida",
                "batch_id": batch_id,
                "case_id": batch_travado.case_id,
            }

        transicoes_permitidas = TRANSICOES_VALIDAS.get(estado_atual, [])
        if novo_estado not in transicoes_permitidas:
            return {
                "erro": "transicao_invalida",
                "batch_id": batch_id,
                "estado_atual": estado_atual,
                "novo_estado": novo_estado,
                "permitidas": transicoes_permitidas,
            }

        agora = datetime.now(timezone.utc)
        dados_atualizacao = {
            DocumentIntakeBatch.ciclo_vida_estado: novo_estado,
            DocumentIntakeBatch.ciclo_vida_updated_at: agora,
        }
        if novo_estado == ESTADO_TRIAGEM_CONCLUIDA:
            dados_atualizacao[DocumentIntakeBatch.triagem_concluida_por] = user_id
            dados_atualizacao[DocumentIntakeBatch.triagem_concluida_em] = agora

        await db.execute(
            update(DocumentIntakeBatch)
            .where(DocumentIntakeBatch.id == batch_id)
            .values(dados_atualizacao)
        )

        detalhes_auditoria = f"Transição {estado_atual} → {novo_estado}"
        if motivo:
            detalhes_auditoria += f": {motivo}"

        await criar_audit_log(
            db,
            user_id=user_id,
            user_role=user_role,
            acao="MUDAR_CICLO_VIDA",
            entidade="DocumentIntakeBatch",
            registro_id=batch_id,
            detalhes=detalhes_auditoria,
            dados_antes={"ciclo_vida_estado": estado_atual},
            dados_depois={"ciclo_vida_estado": novo_estado},
        )

        await db.commit()

        return {
            "sucesso": True,
            "batch_id": batch_id,
            "estado_anterior": estado_atual,
            "estado_novo": novo_estado,
        }
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning(
            "[dpt360_lifecycle] mudar_estado falhou para %s (%s)",
            batch_id,
            type(exc).__name__,
        )
        return {"erro": type(exc).__name__}


async def anonimizar_oportunidade(
    db,
    batch_id: str,
) -> dict[str, Any]:
    """Remove PII de uma oportunidade descartada/expirada.

    Chamado pelo job de anonimização automática. Sob SELECT...FOR UPDATE:
    - Revalida estado (descartada/expirada) e case_id IS NULL
    - Remove email, telefone, mensagem, contato de resultado[dpt360_opportunity]
    - Preserva origem, urgencia_declarada, status, assunto, empresa
    - Marca anonimizada_em = NOW()

    Registra auditoria (ação, batch ID, timestamp; sem PII).
    """
    try:
        batch_travado = (
            await db.execute(
                select(DocumentIntakeBatch)
                .where(DocumentIntakeBatch.id == batch_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

        if batch_travado is None:
            logger.warning("[dpt360_lifecycle] batch %s não existe", batch_id)
            return {"erro": "batch_nao_encontrado"}

        if batch_travado.case_id is not None:
            logger.warning(
                "[dpt360_lifecycle] batch %s tem case_id — pulado",
                batch_id,
            )
            return {"erro": "batch_vinculado_a_caso"}

        estado = batch_travado.ciclo_vida_estado or ESTADO_TRIAGEM_PENDENTE
        if estado not in (ESTADO_DESCARTADA, ESTADO_EXPIRADA):
            return {
                "erro": "estado_nao_elegivel_anonimizacao",
                "batch_id": batch_id,
                "estado": estado,
            }

        if batch_travado.anonimizada_em is not None:
            return {
                "sucesso": True,
                "batch_id": batch_id,
                "ja_anonimizada_em": batch_travado.anonimizada_em.isoformat(),
            }

        resultado = batch_travado.resultado
        if isinstance(resultado, dict):
            opp = resultado.get("dpt360_opportunity", {})
            if isinstance(opp, dict):
                opp_copia = dict(opp)
                for chave_sensivel in ("email", "telefone", "mensagem", "contato"):
                    opp_copia.pop(chave_sensivel, None)
                resultado = dict(resultado)
                resultado["dpt360_opportunity"] = opp_copia
                batch_travado.resultado = resultado

        agora = datetime.now(timezone.utc)

        await db.execute(
            update(DocumentIntakeBatch)
            .where(DocumentIntakeBatch.id == batch_id)
            .values({
                DocumentIntakeBatch.resultado: resultado,
                DocumentIntakeBatch.anonimizada_em: agora,
                DocumentIntakeBatch.ciclo_vida_estado: ESTADO_ANONIMIZADA,
                DocumentIntakeBatch.ciclo_vida_updated_at: agora,
            })
        )

        await criar_audit_log(
            db,
            user_id=None,
            user_role=None,
            acao="ANONIMIZAR",
            entidade="DocumentIntakeBatch",
            registro_id=batch_id,
            detalhes=f"Job de anonimização automática (estado: {estado})",
            dados_depois={"anonimizada_em": agora.isoformat()},
        )

        await db.commit()

        return {
            "sucesso": True,
            "batch_id": batch_id,
            "anonimizada_em": agora.isoformat(),
        }
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning(
            "[dpt360_lifecycle] anonimizar falhou para %s (%s)",
            batch_id,
            type(exc).__name__,
        )
        return {"erro": type(exc).__name__}


async def expurgar_oportunidade(
    db,
    batch_id: str,
) -> dict[str, Any]:
    """Remove completamente uma oportunidade anonimizada.

    Chamado pelo job de expurgo automático. Sob SELECT...FOR UPDATE:
    - Revalida estado = anonimizada e case_id IS NULL
    - Deleta DocumentIntakeItem, Document, DocumentIntakeBatch
    - Registra auditoria (ID, timestamp; sem nenhum dado pessoal)
    """
    try:
        batch_travado = (
            await db.execute(
                select(DocumentIntakeBatch)
                .where(DocumentIntakeBatch.id == batch_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

        if batch_travado is None:
            logger.warning("[dpt360_lifecycle] batch %s não existe", batch_id)
            return {"erro": "batch_nao_encontrado"}

        if batch_travado.case_id is not None:
            logger.warning(
                "[dpt360_lifecycle] batch %s tem case_id — pulado",
                batch_id,
            )
            return {"erro": "batch_vinculado_a_caso"}

        estado = batch_travado.ciclo_vida_estado or ESTADO_TRIAGEM_PENDENTE
        if estado != ESTADO_ANONIMIZADA:
            return {
                "erro": "estado_nao_elegivel_expurgo",
                "batch_id": batch_id,
                "estado": estado,
            }

        itens = (
            await db.execute(
                select(DocumentIntakeItem).where(
                    DocumentIntakeItem.batch_id == batch_id
                )
            )
        ).scalars().all()

        documentos_removidos = 0
        bytes_liberados = 0
        settings = get_settings()
        upload_root = os.path.realpath(settings.UPLOAD_DIR)

        for item in itens:
            doc = await db.get(Document, item.document_id)
            if doc is not None and (doc.case_id is None and doc.client_id is None):
                full_path = os.path.realpath(
                    os.path.join(settings.UPLOAD_DIR, doc.filepath or "")
                )
                if full_path.startswith(upload_root + os.sep):
                    try:
                        os.remove(full_path)
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        logger.warning(
                            "[dpt360_lifecycle] falha ao remover arquivo de %s (%s)",
                            doc.id,
                            exc,
                        )
                bytes_liberados += doc.size_bytes or 0
                await db.delete(doc)
                documentos_removidos += 1
                await db.delete(item)
            elif doc is None:
                await db.delete(item)

        await db.delete(batch_travado)

        await criar_audit_log(
            db,
            user_id=None,
            user_role=None,
            acao="EXPURGAR",
            entidade="DocumentIntakeBatch",
            registro_id=batch_id,
            detalhes="Job de expurgo automático (anonimizada)",
        )

        await db.commit()

        return {
            "sucesso": True,
            "batch_id": batch_id,
            "documentos_removidos": documentos_removidos,
            "bytes_liberados": bytes_liberados,
        }
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning(
            "[dpt360_lifecycle] expurgar falhou para %s (%s)",
            batch_id,
            type(exc).__name__,
        )
        return {"erro": type(exc).__name__}


async def job_anonimizar_oportunidades(
    db,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Job automático: anonimiza oportunidades descartadas/expiradas após prazos.

    Seleção:
    - modalidade = dpt360_oportunidade
    - ciclo_vida_estado IN (descartada, expirada)
    - ciclo_vida_updated_at < NOW() - PRAZO_DESCARTADA
    - anonimizada_em IS NULL
    - case_id IS NULL

    dry_run=True: apenas conta (relatório)
    dry_run=False: executa anonimização
    """
    try:
        agora = datetime.now(timezone.utc)
        corte = agora - timedelta(days=PRAZO_DESCARTADA)

        batches = (
            await db.execute(
                select(DocumentIntakeBatch).where(
                    DocumentIntakeBatch.modalidade == "dpt360_oportunidade",
                    DocumentIntakeBatch.ciclo_vida_estado.in_(
                        (ESTADO_DESCARTADA, ESTADO_EXPIRADA)
                    ),
                    DocumentIntakeBatch.ciclo_vida_updated_at < corte,
                    DocumentIntakeBatch.anonimizada_em.is_(None),
                    DocumentIntakeBatch.case_id.is_(None),
                )
            )
        ).scalars().all()

        anonimizadas = 0
        erros = 0

        for batch in batches:
            if dry_run:
                anonimizadas += 1
            else:
                resultado = await anonimizar_oportunidade(db, batch.id)
                if resultado.get("sucesso"):
                    anonimizadas += 1
                else:
                    erros += 1
                    logger.warning(
                        "[dpt360_lifecycle] erro ao anonimizar %s: %s",
                        batch.id,
                        resultado.get("erro"),
                    )

        return {
            "dry_run": dry_run,
            "anonimizadas": anonimizadas,
            "erros": erros,
            "corte": corte.isoformat(),
        }
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning(
            "[dpt360_lifecycle] job_anonimizar falhou (%s)",
            type(exc).__name__,
        )
        return {"erro": type(exc).__name__}


async def job_expurgar_oportunidades(
    db,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Job automático: expurga oportunidades anonimizadas após 30 dias.

    Seleção:
    - modalidade = dpt360_oportunidade
    - ciclo_vida_estado = anonimizada
    - anonimizada_em < NOW() - 30 dias
    - case_id IS NULL

    dry_run=True: apenas conta (relatório)
    dry_run=False: executa expurgo
    """
    try:
        agora = datetime.now(timezone.utc)
        corte = agora - timedelta(days=PRAZO_ANONIMIZADA)

        batches = (
            await db.execute(
                select(DocumentIntakeBatch).where(
                    DocumentIntakeBatch.modalidade == "dpt360_oportunidade",
                    DocumentIntakeBatch.ciclo_vida_estado == ESTADO_ANONIMIZADA,
                    DocumentIntakeBatch.anonimizada_em < corte,
                    DocumentIntakeBatch.case_id.is_(None),
                )
            )
        ).scalars().all()

        expurgadas = 0
        bytes_liberados = 0
        erros = 0

        for batch in batches:
            if dry_run:
                expurgadas += 1
            else:
                resultado = await expurgar_oportunidade(db, batch.id)
                if resultado.get("sucesso"):
                    expurgadas += 1
                    bytes_liberados += resultado.get("bytes_liberados", 0)
                else:
                    erros += 1
                    logger.warning(
                        "[dpt360_lifecycle] erro ao expurgar %s: %s",
                        batch.id,
                        resultado.get("erro"),
                    )

        return {
            "dry_run": dry_run,
            "expurgadas": expurgadas,
            "bytes_liberados": bytes_liberados,
            "erros": erros,
            "corte": corte.isoformat(),
        }
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning(
            "[dpt360_lifecycle] job_expurgar falhou (%s)",
            type(exc).__name__,
        )
        return {"erro": type(exc).__name__}
