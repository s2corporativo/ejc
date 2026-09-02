"""Serviço de rescan/backfill de SHA-256 de documentos.

Recalcula o SHA-256 de documentos vigentes, compara com o hash probatório
persistido no próprio ``Document`` e, quando houver, com o último intake. O
resultado alimenta tanto as tabelas históricas de rescan quanto o estado simples
de integridade exibido pelo GED.

Nenhuma divergência inclui filepath ou conteúdo documental.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.services import document_hash_service
from app.services.document_remote_hash_service import (
    ConfiguracaoHashRclone,
    HashRemotoConfiguracaoError,
    HashRemotoIndisponivelError,
    calcular_sha256_remoto_rclone,
)

logger = logging.getLogger("ejc.services.document_rescan")

FATIA_LIMITE = 50


@dataclass(frozen=True)
class RescanResultado:
    batch_id: str
    itens_processados: int = 0
    itens_concluidos: int = 0
    itens_erro: int = 0
    itens_nao_disponiveis: int = 0
    divergencias: list[dict] = field(default_factory=list)


class _SemFonteRemotaError(RuntimeError):
    pass


def _motivo_divergencia(erro: Exception) -> str | None:
    if isinstance(erro, document_hash_service.HashArquivoIndisponivelError):
        return "arquivo_ausente"
    if isinstance(erro, document_hash_service.HashMetadataMismatchError):
        return "tamanho_divergente"
    if isinstance(erro, document_hash_service.HashPathInvalidoError):
        return "caminho_invalido"
    if isinstance(erro, (HashRemotoIndisponivelError, HashRemotoConfiguracaoError)):
        return "infraestrutura_remota"
    return None


async def _hashar_documento(documento, upload_root: Path, rclone_config):
    if documento.drive_file_id:
        if not rclone_config:
            raise _SemFonteRemotaError()
        config = (
            rclone_config
            if isinstance(rclone_config, ConfiguracaoHashRclone)
            else ConfiguracaoHashRclone(**rclone_config)
        )
        return await calcular_sha256_remoto_rclone(
            config,
            documento.filepath,
            expected_size=documento.size_bytes,
        )
    return await document_hash_service.calcular_sha256_local(
        upload_root,
        documento.filepath,
        expected_size=documento.size_bytes,
    )


async def _processar_item(documento, upload_root: Path, rclone_config, itens: list[dict]) -> None:
    try:
        calculado = await _hashar_documento(documento, upload_root, rclone_config)
    except _SemFonteRemotaError:
        itens.append({"document_id": documento.id, "motivo": "sem_fonte_remota", "status": "erro"})
        return
    except document_hash_service.HashArquivoIndisponivelError:
        itens.append({"document_id": documento.id, "motivo": "arquivo_ausente", "status": "nao_disponivel"})
        return
    except document_hash_service.HashMetadataMismatchError:
        itens.append({"document_id": documento.id, "motivo": "tamanho_divergente", "status": "erro"})
        return
    except Exception as excecao:
        motivo = _motivo_divergencia(excecao) or "infraestrutura_generica"
        logger.warning(
            "Falha pontual no rescan; document_id=%s exception_type=%s",
            documento.id,
            type(excecao).__name__,
        )
        itens.append({"document_id": documento.id, "motivo": motivo, "status": "erro"})
        return
    itens.append({
        "document_id": documento.id,
        "motivo": "",
        "status": "concluido",
        "sha256_calculado": calculado.sha256,
    })


async def _enriquecer_divergencias(
    db,
    itens: list[dict],
    documentos_map: dict[str, object],
    batch_id: str = "",
) -> None:
    """Compara hash físico com ``Document.sha256`` e intake e persiste estados."""
    agora = datetime.now(timezone.utc)
    for item in itens:
        documento = documentos_map.get(item["document_id"])
        sha_intake = None

        if item["status"] == "concluido":
            calculado = item.get("sha256_calculado")
            sha_registrado = getattr(documento, "sha256", None) if documento else None
            if sha_registrado:
                if calculado != sha_registrado:
                    item["motivo"] = "diverge_do_documento"
                    if documento is not None:
                        documento.integrity_status = "divergent"
                elif documento is not None:
                    documento.integrity_status = "verified"
            elif documento is not None:
                documento.integrity_status = "legacy_unregistered"

            if documento is not None:
                documento.integrity_verified_at = agora

            try:
                intakes = await buscar_intake_sha(db, item["document_id"])
            except Exception as excecao:
                logger.warning(
                    "Intake indisponível durante rescan; document_id=%s exception_type=%s",
                    item["document_id"],
                    type(excecao).__name__,
                )
                intakes = []
            if intakes:
                sha_intake = (
                    intakes[0].sha256 if hasattr(intakes[0], "sha256")
                    else intakes[0]["sha256"]
                )
                if sha_intake and sha_intake != calculado:
                    if not item["motivo"]:
                        item["motivo"] = "diverge_do_intake"
                    if documento is not None:
                        documento.integrity_status = "divergent"
        elif documento is not None:
            documento.integrity_status = (
                "unavailable" if item["status"] == "nao_disponivel" else "error"
            )
            documento.integrity_verified_at = agora

        try:
            await gravar_item_rescan(
                db,
                batch_id,
                item["document_id"],
                sha256_calculado=item.get("sha256_calculado", ""),
                sha256_intake=sha_intake or "",
                motivo=item["motivo"] or None,
                status=item["status"],
            )
        except Exception as excecao:
            logger.warning(
                "Gravação de item rescan falhou; document_id=%s exception_type=%s",
                item["document_id"],
                type(excecao).__name__,
            )


async def selecionar_documentos(
    db,
    document_ids: list[str] | None = None,
    client_id: str | None = None,
    case_id: str | None = None,
) -> list:
    from sqlalchemy import select
    from app.models.document import Document

    query = select(Document).where(Document.deleted_at.is_(None))
    if document_ids:
        query = query.where(Document.id.in_(document_ids))
    if client_id is not None:
        query = query.where(Document.client_id == client_id)
    if case_id is not None:
        query = query.where(Document.case_id == case_id)
    resultado = await db.execute(query)
    return list(resultado.scalars().all())


async def buscar_intake_sha(db, document_id: str) -> list:
    from sqlalchemy import desc, select
    from app.models.document_intake import DocumentIntakeItem

    query = (
        select(DocumentIntakeItem)
        .where(DocumentIntakeItem.document_id == document_id)
        .order_by(desc(DocumentIntakeItem.created_at))
        .limit(5)
    )
    resultado = await db.execute(query)
    return list(resultado.scalars().all())


async def gravar_item_rescan(
    db,
    batch_id: str,
    document_id: str,
    sha256_calculado: str,
    motivo: str | None,
    status: str,
    sha256_intake: str = "",
) -> None:
    from app.models.document_rescan import DocumentHashRescanItem

    db.add(DocumentHashRescanItem(
        id=_novo_id(),
        batch_id=batch_id,
        document_id=document_id,
        status=status,
        motivo=motivo or None,
        sha256_calculado=sha256_calculado or None,
        sha256_intake=sha256_intake or None,
    ))
    await db.flush()
    await db.commit()


def _novo_id() -> str:
    import uuid
    return uuid.uuid4().hex


async def executar_rescan(
    upload_root: Path | str,
    rclone_config,
    documentos,
    fatia: int = FATIA_LIMITE,
    db=None,
    batch_id: str = "",
) -> RescanResultado:
    _upload_root = Path(upload_root)
    itens: list[dict] = []
    documentos_map = {doc.id: doc for doc in documentos}

    for inicio in range(0, len(documentos), fatia):
        fatia_docs = documentos[inicio : inicio + fatia]
        await asyncio.gather(*[
            _processar_item(doc, _upload_root, rclone_config, itens)
            for doc in fatia_docs
        ])

    if db is not None:
        await _enriquecer_divergencias(db, itens, documentos_map, batch_id)

    erros = sum(1 for item in itens if item["status"] == "erro")
    nao_disponiveis = sum(1 for item in itens if item["status"] == "nao_disponivel")
    concluidos = len(documentos) - erros - nao_disponiveis

    return RescanResultado(
        batch_id=batch_id,
        itens_processados=len(documentos),
        itens_concluidos=concluidos,
        itens_erro=erros,
        itens_nao_disponiveis=nao_disponiveis,
        divergencias=itens,
    )
