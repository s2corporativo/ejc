"""Filtros e paginação neutros para a listagem do GED.

O caller continua responsável por montar a query-base já limitada por RBAC,
ownership e cofre. Este serviço nunca amplia acesso: apenas acrescenta filtros de
negócio, ordenação estável, contagem e paginação.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocConfidencialidade, Document

MAX_BUSCA_CARACTERES = 200
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class FiltrosBuscaDocumentos:
    case_id: str | None = None
    client_id: str | None = None
    search: str | None = None
    tipo: str | None = None
    confidencialidade: DocConfidencialidade | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    classificacao_pendente: bool | None = None


@dataclass(frozen=True, slots=True)
class PaginaDocumentos:
    itens: tuple[Document, ...]
    total: int
    page: int
    page_size: int


def normalizar_busca(search: str | None) -> str | None:
    if search is None:
        return None
    termo = search.strip()
    if not termo:
        return None
    if len(termo) > MAX_BUSCA_CARACTERES:
        raise ValueError("termo de busca excede o limite permitido")
    return termo


def _padrao_ilike_literal(termo: str) -> str:
    """Escapa curingas do usuário; busca é substring literal, não mini-pattern."""

    escapado = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


def validar_paginacao(page: int, page_size: int) -> None:
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page deve ser inteiro positivo")
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= MAX_PAGE_SIZE
    ):
        raise ValueError(f"page_size deve estar entre 1 e {MAX_PAGE_SIZE}")


def aplicar_filtros(
    query: Select[Any],
    filtros: FiltrosBuscaDocumentos,
) -> Select[Any]:
    """Acrescenta filtros sem remover qualquer predicate prévio de autorização."""

    if filtros.case_id:
        query = query.where(Document.case_id == filtros.case_id)
    if filtros.client_id:
        query = query.where(Document.client_id == filtros.client_id)
    if filtros.tipo:
        query = query.where(Document.tipo == filtros.tipo)
    if filtros.confidencialidade is not None:
        query = query.where(Document.confidencialidade == filtros.confidencialidade)

    if filtros.classificacao_pendente is True:
        query = query.where(Document.tipo.is_(None))
    elif filtros.classificacao_pendente is False:
        query = query.where(Document.tipo.is_not(None))

    if filtros.data_inicio:
        query = query.where(
            Document.created_at
            >= datetime.combine(filtros.data_inicio, dtime.min, tzinfo=timezone.utc)
        )
    if filtros.data_fim:
        query = query.where(
            Document.created_at
            < datetime.combine(
                filtros.data_fim + timedelta(days=1),
                dtime.min,
                tzinfo=timezone.utc,
            )
        )

    termo = normalizar_busca(filtros.search)
    if termo:
        pattern = _padrao_ilike_literal(termo)
        query = query.where(
            or_(
                Document.titulo.ilike(pattern, escape="\\"),
                Document.ocr_text.ilike(pattern, escape="\\"),
            )
        )

    # ``id`` desempata timestamps iguais e evita item trocar de página por ordem
    # indefinida. Keyset pode substituir offset numa etapa posterior de escala.
    return query.order_by(Document.created_at.desc(), Document.id.desc())


async def paginar_documentos(
    db: AsyncSession,
    query_base: Select[Any],
    *,
    filtros: FiltrosBuscaDocumentos,
    page: int,
    page_size: int,
) -> PaginaDocumentos:
    validar_paginacao(page, page_size)
    query = aplicar_filtros(query_base, filtros)

    total = int(
        (
            await db.scalar(
                select(func.count()).select_from(query.order_by(None).subquery())
            )
        )
        or 0
    )
    itens = tuple(
        (
            await db.execute(
                query.offset((page - 1) * page_size).limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return PaginaDocumentos(
        itens=itens,
        total=total,
        page=page,
        page_size=page_size,
    )
