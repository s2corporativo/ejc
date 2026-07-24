"""Retrieval RAG com proveniência auditável, sem alterar o ranking existente.

O módulo compõe ``buscar_contexto_rag`` com o contrato de proveniência. Os
metadados dos documentos são carregados em uma única consulta por lote, evitando
N+1. O ranking, os filtros de escopo e os gates de governança continuam sob
responsabilidade exclusiva do serviço canônico de retrieval.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import KnowledgeDoc
from app.services.ai_service import buscar_contexto_rag
from app.services.rag_provenance import normalizar_proveniencia

logger = logging.getLogger("ejc.rag_traceable")


def _doc_para_mapping(doc: KnowledgeDoc) -> dict[str, Any]:
    """Extrai apenas campos necessários ao contrato público de proveniência."""

    return {
        "id": doc.id,
        "titulo": doc.titulo,
        "categoria": doc.categoria,
        "fonte": doc.fonte,
        "tribunal": doc.tribunal,
        "extra": doc.extra,
        "case_id": doc.case_id,
        "chave_origem": doc.chave_origem,
        "hash_conteudo": doc.hash_conteudo,
        "atualizado_em": doc.atualizado_em,
        "versao": doc.versao,
        "vigente": doc.vigente,
        "revisado": doc.revisado,
    }


def _doc_fallback(resultado: Mapping[str, Any], motivo: str) -> dict[str, Any]:
    """Representação mínima quando o documento não pode ser recarregado."""

    return {
        "id": resultado.get("doc_id"),
        "titulo": resultado.get("titulo"),
        "categoria": resultado.get("categoria"),
        "fonte": resultado.get("fonte"),
        "versao": resultado.get("versao"),
        "extra": {
            "proveniencia": {
                "status_fonte": "identificacao_insuficiente",
                "motivo_indisponibilidade": motivo,
            }
        },
    }


def _chunk_para_mapping(resultado: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": resultado.get("chunk_id"),
        "chunk_id": resultado.get("chunk_id"),
        "chunk_index": resultado.get("chunk_index"),
        "conteudo": resultado.get("conteudo"),
        "metadata": resultado.get("metadata"),
        "extra": resultado.get("extra"),
    }


def _anexar_proveniencia(
    resultados: Sequence[Mapping[str, Any]],
    documentos: Mapping[str, Mapping[str, Any]],
    *,
    motivo_fallback: str,
) -> list[dict[str, Any]]:
    saida: list[dict[str, Any]] = []
    for resultado in resultados:
        item = dict(resultado)
        doc_id = str(resultado.get("doc_id") or "")
        doc = documentos.get(doc_id)
        if doc is None:
            doc = _doc_fallback(resultado, motivo_fallback)
        item["proveniencia"] = normalizar_proveniencia(
            doc=doc,
            chunk=_chunk_para_mapping(resultado),
        )
        saida.append(item)
    return saida


async def enriquecer_resultados_com_proveniencia(
    db: AsyncSession,
    resultados: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Anexa proveniência em lote sem modificar ordem, score ou conteúdo."""

    if not resultados:
        return []

    doc_ids = sorted(
        {
            str(resultado.get("doc_id"))
            for resultado in resultados
            if resultado.get("doc_id")
        }
    )
    if not doc_ids:
        return _anexar_proveniencia(
            resultados,
            {},
            motivo_fallback="resultado sem identificador de documento",
        )

    try:
        rows = (
            await db.execute(
                select(KnowledgeDoc).where(KnowledgeDoc.id.in_(doc_ids))
            )
        ).scalars().all()
    except Exception as exc:  # enriquecimento nunca derruba o retrieval já concluído
        logger.warning(
            "Proveniência indisponível; mantendo resultados RAG: %s",
            exc.__class__.__name__,
        )
        return _anexar_proveniencia(
            resultados,
            {},
            motivo_fallback="falha ao carregar metadados de proveniência",
        )

    documentos = {str(doc.id): _doc_para_mapping(doc) for doc in rows}
    return _anexar_proveniencia(
        resultados,
        documentos,
        motivo_fallback="documento de origem não localizado no lote",
    )


async def buscar_contexto_rag_rastreavel(
    db: AsyncSession,
    consulta: str,
    limite: int = 6,
    categorias: list[str] | None = None,
    modo_or: bool = False,
    scope_client_id: str | None = None,
    incluir_historico: bool = False,
    incluir_ficticio: bool = False,
) -> list[dict[str, Any]]:
    """Executa o retrieval canônico e acrescenta proveniência auditável."""

    resultados = await buscar_contexto_rag(
        db,
        consulta,
        limite=limite,
        categorias=categorias,
        modo_or=modo_or,
        scope_client_id=scope_client_id,
        incluir_historico=incluir_historico,
        incluir_ficticio=incluir_ficticio,
    )
    return await enriquecer_resultados_com_proveniencia(db, resultados)
