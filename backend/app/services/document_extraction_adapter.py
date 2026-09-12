"""Extração textual determinística para o fluxo canônico do GED.

A ingestão não deve disparar interpretação jurídica/LLM apenas para obter OCR.
Este adapter usa diretamente o serviço de OCR/XML já existente, enquanto o
arquivo ainda está em staging. A análise estratégica é agendada separadamente
após o commit do ``Document``.

Isso mantém separadas as responsabilidades: prova física -> extração local ->
persistência -> análise IA assíncrona/HITL.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document_ingestion_service import IngestaoDocumentoLocal
from app.services.ocr_service import extrair_texto, extrair_xml

logger = logging.getLogger(__name__)


class StatusExtracaoTexto(StrEnum):
    SUCESSO = "success"
    SEM_TEXTO = "empty"
    INDISPONIVEL = "unavailable"


@dataclass(frozen=True, slots=True)
class ResultadoExtracaoTexto:
    status: StatusExtracaoTexto
    ocr_text: str | None = None
    nfe: dict | None = None


def _normalizar_texto(texto: object, *, nfe: dict | None = None) -> ResultadoExtracaoTexto:
    if texto is None:
        return ResultadoExtracaoTexto(StatusExtracaoTexto.SEM_TEXTO, nfe=nfe)
    if not isinstance(texto, str):
        return ResultadoExtracaoTexto(StatusExtracaoTexto.INDISPONIVEL, nfe=nfe)
    if not texto.strip():
        return ResultadoExtracaoTexto(StatusExtracaoTexto.SEM_TEXTO, nfe=nfe)
    return ResultadoExtracaoTexto(StatusExtracaoTexto.SUCESSO, ocr_text=texto, nfe=nfe)


async def extrair_texto_compatibilidade(
    db: AsyncSession,
    ingestao: IngestaoDocumentoLocal,
    *,
    user_id: str | None,
) -> ResultadoExtracaoTexto:
    """Extrai OCR/XML do staging sem chamar LLM ou RAG.

    ``db`` e ``user_id`` permanecem no contrato temporariamente para evitar
    quebra dos callers do orquestrador durante o cutover. Não são usados nesta
    camada determinística.
    """

    del db, user_id
    caminho = ingestao.storage.caminho_staging_para_validacao
    try:
        if ingestao.ext == ".xml":
            resultado = await asyncio.to_thread(extrair_xml, str(caminho))
            if not resultado:
                return ResultadoExtracaoTexto(StatusExtracaoTexto.SEM_TEXTO)
            nfe = resultado.get("nfe") if isinstance(resultado.get("nfe"), dict) else None
            return _normalizar_texto(resultado.get("texto"), nfe=nfe)

        texto = await asyncio.to_thread(
            extrair_texto,
            str(caminho),
            ingestao.mimetype,
        )
        return _normalizar_texto(texto)
    except Exception as exc:
        logger.warning(
            "Extração textual documental indisponível; exception_type=%s",
            type(exc).__name__,
        )
        return ResultadoExtracaoTexto(StatusExtracaoTexto.INDISPONIVEL)
