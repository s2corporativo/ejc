"""Serviço de rescan/backfill de SHA-256 de documentos (Épico #1019 A3.2).

Recalcula o SHA-256 de documentos vigentes e grava o resultado nas tabelas
``document_hash_rescan_batches`` / ``document_hash_rescan_items`` (migration
142). Usa as primitivas já existentes:

- ``document_hash_service.calcular_sha256_local`` para arquivos locais;
- ``document_remote_hash_service.calcular_sha256_remoto_rclone`` para
  documentos no Drive (``drive_file_id`` presente).

Contrato: ``executar_rescan(upload_root, rclone_config, documentos)`` retorna
``RescanResultado`` com contagens por status e ``divergencias`` — cada
divergência carrega ``document_id``, ``motivo`` e hashes, **nunca** filepath
ou dados pessoais (LGPD). Lote nunca aborta por item individual: itens
ausentes/indisponíveis viram ``nao_disponivel``, erros de cálculo viram
``erro`` com motivo classificado.

Os pontos de banco (``selecionar_documentos``, ``buscar_intake_sha``,
``gravar_item_rescan``) vivem neste módulo como funções independentes de
módulo — mockáveis nos testes unitários — e são o ponto de fiação do
dispatch (Celery/BackgroundTasks) no PR de integração.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.services import document_hash_service
from app.services.document_remote_hash_service import (
    ConfiguracaoHashRclone,
    calcular_sha256_remoto_rclone,
    HashRemotoConfiguracaoError,
    HashRemotoIndisponivelError,
)

logger = logging.getLogger("ejc.services.document_rescan")

FATIA_LIMITE = 50


@dataclass(frozen=True)
class RescanResultado:
    """Resultado de um rescan: contagens por status + divergências."""

    batch_id: str
    itens_processados: int = 0
    itens_concluidos: int = 0
    itens_erro: int = 0
    itens_nao_disponiveis: int = 0
    divergencias: list[dict] = field(default_factory=list)


class _SemFonteRemotaError(RuntimeError):
    """Documento no Drive sem configuração rclone — item recusado de forma
    segura (nunca cai em hash local com filepath ``drive:...``)."""


def _motivo_divergencia(erro: Exception) -> str | None:
    """Classifica a exceção da fonte de hash em motivo LGPD-safe.
    ``None`` = erro não esperado (infraestrutura genérica)."""
    if isinstance(erro, document_hash_service.HashArquivoIndisponivelError):
        return "arquivo_ausente"
    if isinstance(erro, document_hash_service.HashMetadataMismatchError):
        return "tamanho_divergente"
    if isinstance(erro, document_hash_service.HashPathInvalidoError):
        return "caminho_invalido"
    if isinstance(
        erro, (HashRemotoIndisponivelError, HashRemotoConfiguracaoError)
    ):
        return "infraestrutura_remota"
    return None


async def _hashar_documento(
    documento,
    upload_root: Path,
    rclone_config,
) -> document_hash_service.HashDocumentoCalculado:
    """Fonte de hash condicional: local ou remota. Nunca faz fallback
    inseguro de filepath ``drive:...`` para o hash local."""
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


async def _processar_item(
    documento,
    upload_root: Path,
    rclone_config,
    itens: list[dict],
) -> None:
    """Processa um único documento de forma isolada: qualquer falha vira
    divergência classificada; ``CancelledError`` é propagado para permitir
    cancelamento ordenado do lote."""
    try:
        calculado = await _hashar_documento(documento, upload_root, rclone_config)
    except _SemFonteRemotaError:
        itens.append({
            "document_id": documento.id,
            "motivo": "sem_fonte_remota",
            "status": "erro",
        })
        return
    except document_hash_service.HashArquivoIndisponivelError:
        itens.append({
            "document_id": documento.id,
            "motivo": "arquivo_ausente",
            "status": "nao_disponivel",
        })
        return
    except document_hash_service.HashMetadataMismatchError:
        itens.append({
            "document_id": documento.id,
            "motivo": "tamanho_divergente",
            "status": "erro",
        })
        return
    except Exception as excecao:
        motivo = _motivo_divergencia(excecao) or "infraestrutura_generica"
        logger.exception("falha pontual no rescan de %s", documento.id)
        itens.append({
            "document_id": documento.id,
            "motivo": motivo,
            "status": "erro",
        })
        return
    itens.append({
        "document_id": documento.id,
        "motivo": "",
        "status": "concluido",
        "sha256_calculado": calculado.sha256,
    })


async def _enriquecer_divergencias(
    db, itens: list[dict], documentos_map: dict[str, str], batch_id: str = "",
) -> None:
    """Compara o SHA calculado com o último intake de cada item concluído
    e marca ``diverge_do_intake`` quando houver diferença — mantendo o
    hash de intake para triagem humana, sem path ou CPF (LGPD)."""
    for item in itens:
        if item["status"] == "concluido":
            try:
                intakes = await buscar_intake_sha(db, item["document_id"])
            except Exception as excecao:  # falha pontual não derruba o lote
                logger.warning(
                    "[rescan] intake indisponível (%s: %s) para documento %s",
                    type(excecao).__name__, str(excecao)[:100],
                    item["document_id"],
                )
                intakes = []
            if intakes:
                ultimo_intake = (
                    intakes[0].sha256 if hasattr(intakes[0], "sha256")
                    else intakes[0]["sha256"]
                )
                if ultimo_intake and ultimo_intake != item["sha256_calculado"]:
                    item["motivo"] = "diverge_do_intake"
                    item["sha256_intake"] = ultimo_intake
                else:
                    item["sha256_intake"] = ultimo_intake or ""
        # Grava o item do lote independentemente do status/motivo.
        try:
            await gravar_item_rescan(
                db,
                batch_id,
                item["document_id"],
                sha256_calculado=item.get("sha256_calculado", ""),
                motivo=item["motivo"] or None,
                status=item["status"],
            )
        except Exception as excecao:
            logger.warning(
                "[rescan] gravação falhou (%s: %s) para documento %s",
                type(excecao).__name__, str(excecao)[:100],
                item["document_id"],
            )


# ──────────────────────── Pontos de fiação (mockáveis) ────────────────────


async def selecionar_documentos(
    db,
    document_ids: list[str] | None = None,
    client_id: str | None = None,
    case_id: str | None = None,
) -> list:
    """Seleciona documentos vigentes (``deleted_at IS NULL``) — fonte única
    de alvos do rescan."""
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


async def buscar_intake_sha(
    db, document_id: str,
) -> list:
    """Retorna os itens de intake mais recentes (desc por ``created_at``)
    do documento — para comparação com o SHA recalculado."""
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
    motivo: str,
    status: str,
) -> None:
    """Grava ``document_hash_rescan_items`` com commit próprio por item."""
    from app.models.document_rescan import DocumentHashRescanItem

    db.add(DocumentHashRescanItem(
        id=_novo_id(),
        batch_id=batch_id,
        document_id=document_id,
        status=status,
        motivo=motivo or None,
        sha256_calculado=sha256_calculado or None,
    ))
    await db.flush()
    await db.commit()


def _novo_id() -> str:
    """Id UUID-4 sem hífen, compatível com o padrão do repositório."""
    import uuid
    return uuid.uuid4().hex


# ──────────────────────────── Orquestração do lote ───────────────────────


async def executar_rescan(
    upload_root: Path | str,
    rclone_config,
    documentos,
    fatia: int = FATIA_LIMITE,
    db=None,
    batch_id: str = "",
) -> RescanResultado:
    """Recalcula SHA-256 dos ``documentos`` e devolve ``RescanResultado``.
    Cada item é processado de forma isolada: falhas individuais viram
    divergências classificadas, sem abortar o lote. Cancelamento propagado
    para encerramento ordenado (``documentos`` é a fonte única de alvos).

    Quando ``db`` é informado, compara o hash calculado com o último intake
    (``buscar_intake_sha``), marca ``diverge_do_intake`` e grava o item do
    lote (``gravar_item_rescan``). Sem ``db`` o serviço funciona como
    primitiva pura — útil em testes unitários e backfill sem banco."""
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
    nao_disponiveis = sum(
        (1 for item in itens if item["status"] == "nao_disponivel"),
    )
    concluidos = len(documentos) - erros - nao_disponiveis

    return RescanResultado(
        batch_id=batch_id,
        itens_processados=len(documentos),
        itens_concluidos=concluidos,
        itens_erro=erros,
        itens_nao_disponiveis=nao_disponiveis,
        divergencias=itens,
    )
