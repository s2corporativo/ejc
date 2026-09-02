"""Serviços de experiência documental sem regra HTTP.

Mantém a UX simples sem deslocar autorização para o frontend. A consulta de
visibilidade replica o contrato canônico do GED: cofre por papel, cliente
externo isolado ao próprio cliente e equipe não gestora limitada aos casos em
que atua.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.security import ROLE_LEVEL
from app.models.case import Case
from app.models.client import Client
from app.models.document import Document
from app.models.user import User

ANALISE_ATENCAO = {"failed", "stale"}
INTEGRIDADE_ATENCAO = {"divergent", "error", "unavailable"}
MALWARE_ATENCAO = {"infected", "error", "unavailable"}
ANALISE_PROCESSANDO = {"pending", "processing"}
MALWARE_PROCESSANDO = {"pending", "processing"}


def pode_acessar_confidencial(user: User, confidencialidade: str) -> bool:
    if confidencialidade in {"restrito", "confidencial", "segredo_justica"}:
        return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]
    return True


async def verificar_acesso_cliente_sem_caso(
    db: AsyncSession,
    user: User,
    client_id: str,
) -> None:
    if is_gestao(user):
        return
    if user.role.value == "cliente_externo":
        if getattr(user, "client_id", None) == client_id:
            return
        raise HTTPException(status_code=403, detail="Sem permissão para este cliente")
    case_id = await db.scalar(
        select(Case.id)
        .where(
            Case.client_id == client_id,
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == user.id,
                Case.advogado_auxiliar_id == user.id,
            ),
        )
        .limit(1)
    )
    if case_id is None:
        raise HTTPException(status_code=403, detail="Sem permissão para este cliente")


async def verificar_acesso_documento(
    db: AsyncSession,
    user: User,
    document: Document,
) -> None:
    if document.case_id:
        await verificar_acesso_caso(db, user, document.case_id)
        return
    if is_gestao(user) or document.uploaded_by == user.id:
        return
    if document.client_id:
        conf = getattr(document.confidencialidade, "value", document.confidencialidade)
        if user.role.value == "cliente_externo" and conf != "normal":
            raise HTTPException(status_code=403, detail="Documento interno ou restrito")
        await verificar_acesso_cliente_sem_caso(db, user, document.client_id)
        return
    raise HTTPException(status_code=403, detail="Sem permissão para este documento")


async def resolver_contexto_upload(
    db: AsyncSession,
    user: User,
    *,
    case_id: str | None,
    client_id: str | None,
    predecessor: Document | None,
) -> tuple[str | None, str | None]:
    if predecessor is not None:
        await verificar_acesso_documento(db, user, predecessor)
        conf = getattr(predecessor.confidencialidade, "value", predecessor.confidencialidade)
        if not pode_acessar_confidencial(user, conf):
            raise HTTPException(status_code=403, detail="Documento predecessor restrito — acesso negado")
        if case_id is None:
            case_id = predecessor.case_id
        if client_id is None:
            client_id = predecessor.client_id
        if case_id != predecessor.case_id or client_id != predecessor.client_id:
            raise HTTPException(
                status_code=422,
                detail="Nova versão deve manter o mesmo caso/cliente do predecessor",
            )

    if case_id:
        case = await verificar_acesso_caso(db, user, case_id)
        if client_id and case.client_id and client_id != case.client_id:
            raise HTTPException(status_code=422, detail="client_id não corresponde ao cliente do caso")
        client_id = case.client_id
    elif client_id:
        await verificar_acesso_cliente_sem_caso(db, user, client_id)
        existe = await db.scalar(
            select(Client.id).where(Client.id == client_id, Client.deleted_at.is_(None))
        )
        if not existe:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return case_id, client_id


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
