"""Serviços de experiência documental sem regra HTTP.

Mantém a UX simples sem deslocar autorização para o frontend. A consulta de
visibilidade replica o contrato canônico do GED: cofre por papel, cliente
externo isolado ao próprio cliente e equipe não gestora limitada aos casos em
que atua.
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import is_gestao
from app.core.security import ROLE_LEVEL
from app.models.case import Case
from app.models.document import Document
from app.models.user import User

ANALISE_ATENCAO = {"failed", "stale"}
INTEGRIDADE_ATENCAO = {"divergent", "error", "unavailable"}
MALWARE_ATENCAO = {"infected", "error", "unavailable"}
ANALISE_PROCESSANDO = {"pending", "processing"}
MALWARE_PROCESSANDO = {"pending", "processing"}


def motivos_atencao(document: Document) -> list[str]:
    """Retorna códigos estáveis e sem PII para itens que exigem ação humana."""

    motivos: list[str] = []
    if not document.case_id:
        motivos.append("sem_caso")
    if not document.tipo:
        motivos.append("sem_tipo")
    if document.analysis_status in ANALISE_ATENCAO:
        motivos.append("analise_falhou")
    if document.integrity_status in INTEGRIDADE_ATENCAO:
        motivos.append("integridade_atencao")
    if document.malware_scan_status in MALWARE_ATENCAO:
        motivos.append("seguranca_atencao")
    return motivos


def status_operacional(document: Document) -> str:
    """Traduz estados técnicos para `ready|processing|attention`."""

    if motivos_atencao(document):
        return "attention"
    if document.analysis_status in ANALISE_PROCESSANDO:
        return "processing"
    if document.malware_scan_status in MALWARE_PROCESSANDO:
        return "processing"
    return "ready"


def aplicar_visibilidade_documentos(query, user: User):
    """Aplica o mesmo escopo de leitura do GED antes de qualquer filtro UX."""

    if ROLE_LEVEL.get(user.role.value, 0) < ROLE_LEVEL["socio"]:
        query = query.where(Document.confidencialidade.in_(["normal", "interno"]))

    if user.role.value == "cliente_externo":
        client_id = getattr(user, "client_id", None)
        if not client_id:
            return query.where(Document.id.is_(None))
        return query.where(
            Document.client_id == client_id,
            Document.confidencialidade == "normal",
        )

    if is_gestao(user):
        return query

    casos_visiveis = select(Case.id).where(
        Case.deleted_at.is_(None),
        or_(
            Case.advogado_responsavel_id == user.id,
            Case.advogado_auxiliar_id == user.id,
        ),
    )
    clientes_visiveis = select(Case.client_id).where(
        Case.deleted_at.is_(None),
        Case.client_id.is_not(None),
        or_(
            Case.advogado_responsavel_id == user.id,
            Case.advogado_auxiliar_id == user.id,
        ),
    )
    return query.where(
        or_(
            Document.case_id.in_(casos_visiveis),
            Document.case_id.is_(None) & Document.client_id.in_(clientes_visiveis),
            Document.case_id.is_(None)
            & Document.client_id.is_(None)
            & (Document.uploaded_by == user.id),
        )
    )


def filtro_caixa_entrada():
    """Expressão SQL para documentos ativos que exigem ação operacional."""

    return or_(
        Document.case_id.is_(None),
        Document.tipo.is_(None),
        Document.analysis_status.in_(sorted(ANALISE_ATENCAO)),
        Document.integrity_status.in_(sorted(INTEGRIDADE_ATENCAO)),
        Document.malware_scan_status.in_(sorted(MALWARE_ATENCAO)),
    )


async def buscar_duplicado_exato_contexto(
    db: AsyncSession,
    *,
    sha256: str,
    case_id: str | None,
    client_id: str | None,
    uploaded_by: str | None,
) -> Document | None:
    """Busca SHA idêntico somente dentro do contexto já autorizado do upload."""

    query = select(Document).where(
        Document.deleted_at.is_(None),
        Document.sha256 == sha256,
    )
    if case_id:
        query = query.where(Document.case_id == case_id)
    elif client_id:
        query = query.where(
            Document.case_id.is_(None),
            Document.client_id == client_id,
        )
    else:
        query = query.where(
            Document.case_id.is_(None),
            Document.client_id.is_(None),
            Document.uploaded_by == uploaded_by,
        )
    return await db.scalar(query.order_by(Document.created_at.desc(), Document.id.desc()).limit(1))
