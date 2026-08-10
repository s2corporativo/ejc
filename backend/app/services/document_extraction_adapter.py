"""Adapter de compatibilidade para extração textual no fluxo GED.

O router atual usa ``documento_service.extrair_e_analisar`` e aproveita apenas o
campo interno ``_texto_sanitizado``. Esta camada encapsula exatamente esse
contrato existente para retirar a regra do router e manter o arquivo em staging
até a persistência.

Ela NÃO declara resolvido o custo de IA do serviço legado. A separação do
extrator/OCR baixo nível será uma etapa posterior, somente após confirmar sua API
canônica. Nenhum resultado de análise jurídica/IA é retornado por este adapter.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import documento_service
from app.services.document_ingestion_service import IngestaoDocumentoLocal

logger = logging.getLogger(__name__)


class StatusExtracaoTexto(StrEnum):
    SUCESSO = "success"
    SEM_TEXTO = "empty"
    INDISPONIVEL = "unavailable"


@dataclass(frozen=True, slots=True)
class ResultadoExtracaoTexto:
    status: StatusExtracaoTexto
    ocr_text: str | None = None


def _resultado_sanitizado(resultado: object) -> ResultadoExtracaoTexto:
    if not isinstance(resultado, dict):
        return ResultadoExtracaoTexto(StatusExtracaoTexto.INDISPONIVEL)

    texto = resultado.get("_texto_sanitizado")
    if texto is None:
        return ResultadoExtracaoTexto(StatusExtracaoTexto.SEM_TEXTO)
    if not isinstance(texto, str):
        return ResultadoExtracaoTexto(StatusExtracaoTexto.INDISPONIVEL)

    normalizado = texto.strip()
    if not normalizado:
        return ResultadoExtracaoTexto(StatusExtracaoTexto.SEM_TEXTO)
    return ResultadoExtracaoTexto(
        status=StatusExtracaoTexto.SUCESSO,
        ocr_text=texto,
    )


async def extrair_texto_compatibilidade(
    db: AsyncSession,
    ingestao: IngestaoDocumentoLocal,
    *,
    user_id: str | None,
) -> ResultadoExtracaoTexto:
    """Extrai texto sanitizado enquanto o arquivo permanece em quarentena.

    Falhas do extrator legado são fail-soft como no upload atual, mas a mensagem
    bruta da exceção nunca é retornada ou logada. ``CancelledError`` não é
    capturado (herda de BaseException) e portanto continua cancelando o fluxo e
    permitindo que a UoW externa compense o staging.
    """

    caminho = ingestao.storage.caminho_staging_para_validacao
    try:
        resultado = await documento_service.extrair_e_analisar(
            str(caminho),
            ingestao.mimetype,
            db=db,
            enriquecer_rag=False,
            user_id=user_id,
        )
    except Exception as exc:
        logger.warning(
            "Extração textual documental indisponível; exception_type=%s",
            type(exc).__name__,
        )
        return ResultadoExtracaoTexto(StatusExtracaoTexto.INDISPONIVEL)

    return _resultado_sanitizado(resultado)
