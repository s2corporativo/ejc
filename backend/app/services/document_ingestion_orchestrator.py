"""Orquestração canônica da ingestão documental local.

Entry point interno para substituir gradualmente a orquestração hoje espalhada
no router GED. Não faz autorização: o caller deve construir
``DadosPersistenciaDocumento`` somente depois de RBAC/ownership/cofre.

Pipeline:

    stream -> staging -> MIME -> malware -> extração -> versão -> promoção
    -> Document + AuditLog -> commit -> confirmação física

O arquivo permanece em quarentena durante scan e extração. Qualquer exceção ou
cancelamento antes da confirmação final é compensado pela UoW.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.services.document_extraction_adapter import (
    ResultadoExtracaoTexto,
    extrair_texto_compatibilidade,
)
from app.services.document_ingestion_service import preparar_ingestao_documento_local
from app.services.document_persistence_service import (
    ConteudoDocumentoPreparado,
    DadosPersistenciaDocumento,
    persistir_documento_local,
)
from app.services.document_upload_stream import StreamUploadAssincrono
from app.services.malware_scan_service import MalwareScanStatus, ScannerMalware


@dataclass(frozen=True, slots=True)
class ResultadoIngestaoDocumentoLocal:
    documento: Document
    sha256: str
    malware_scan_status: MalwareScanStatus
    extracao: ResultadoExtracaoTexto


async def ingerir_documento_local(
    db: AsyncSession,
    upload: StreamUploadAssincrono,
    *,
    filename: str | None,
    upload_root: Path,
    max_bytes: int,
    dados: DadosPersistenciaDocumento,
    scanner: ScannerMalware | None = None,
    agora: datetime | None = None,
) -> ResultadoIngestaoDocumentoLocal:
    """Executa o lifecycle completo de um upload local já autorizado.

    ``sha256`` e ``malware_scan_status`` são devolvidos apenas no resultado
    interno porque o model atual ainda não possui essas colunas. O caller não
    deve inferir que esses valores foram persistidos até a migration futura.
    """

    ingestao = await preparar_ingestao_documento_local(
        upload,
        filename=filename,
        upload_root=upload_root,
        max_bytes=max_bytes,
        scanner=scanner,
        agora=agora,
    )

    async with ingestao:
        extracao = await extrair_texto_compatibilidade(
            db,
            ingestao,
            user_id=dados.uploaded_by,
        )
        documento = await persistir_documento_local(
            db,
            ingestao,
            dados=dados,
            conteudo=ConteudoDocumentoPreparado(ocr_text=extracao.ocr_text),
        )

    return ResultadoIngestaoDocumentoLocal(
        documento=documento,
        sha256=ingestao.sha256,
        malware_scan_status=ingestao.malware_scan_status,
        extracao=extracao,
    )
