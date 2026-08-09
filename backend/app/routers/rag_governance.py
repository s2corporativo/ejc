"""Rotas administrativas de governança jurídica da Base de Conhecimento.

As rotas não substituem o router RAG existente. Elas consolidam observabilidade,
qualidade, autoridade da fonte, vigência normativa, cobertura por área e testes
do retrieval. Todo o conjunto é restrito aos mesmos perfis gestores que enxergam
a aba administrativa no frontend, evitando acesso por ID a documentos internos.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.rag import KnowledgeDoc
from app.models.user import User
from app.services.ingestion_service import ORIGEM_VIGENCIA_CURADORIA
from app.services.knowledge_governance import (
    AUTHORITY_LABELS,
    LEGAL_STATUS_VALUES,
    compare_versions,
    coverage_matrix,
    document_details,
    health_snapshot,
    inferir_autoridade_documento,
    run_legal_smoke_tests,
    test_document_retrieval,
)

router = APIRouter(prefix="/rag/governanca", tags=["Base de Conhecimento — Governança"])
GOVERNANCE_ROLES = ["superadmin", "admin", "socio"]


AuthorityLevel = Literal[
    "oficial_normativa",
    "precedente_vinculante",
    "jurisprudencia_oficial",
    "oficial_informativa",
    "institucional_interna",
    "doutrinaria",
    "referencial",
]
LegalStatus = Literal[
    "vigente",
    "parcialmente_revogada",
    "revogada",
    "suspensa",
    "vigencia_nao_verificada",
    "nao_aplicavel",
    "historica",
]


class DocumentTestRequest(BaseModel):
    pergunta: str | None = Field(default=None, max_length=1000)
    limite: int = Field(default=8, ge=1, le=20)


class GovernanceMetadataPatch(BaseModel):
    authority_level: AuthorityLevel | None = None
    legal_status: LegalStatus | None = None
    diploma: str | None = Field(default=None, max_length=180)
    numero: str | None = Field(default=None, max_length=80)
    ano: int | None = Field(default=None, ge=1800, le=2200)
    publication_date: str | None = Field(default=None, max_length=40)
    effective_from: str | None = Field(default=None, max_length=40)
    altered_by: str | None = Field(default=None, max_length=500)
    source_official: bool | None = None
    link_official: str | None = Field(default=None, max_length=1000)
    last_verified_at: str | None = Field(default=None, max_length=60)
    area_juridica: str | None = Field(default=None, max_length=120)
    quality_note: str | None = Field(default=None, max_length=1000)
    confirmar_fonte_agora: bool = False


@router.get("/saude")
async def saude_base_conhecimento(
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(require_roles(GOVERNANCE_ROLES)),
):
    """Visão real de documentos utilizáveis, vetores, OCR, duplicidade e frescor."""
    return await health_snapshot(db)


@router.get("/cobertura")
async def cobertura_juridica(
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(require_roles(GOVERNANCE_ROLES)),
):
    """Matriz de cobertura por área e tipo de conhecimento jurídico."""
    return await coverage_matrix(db)


@router.get("/docs/{doc_id}")
async def detalhar_governanca_documento(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(require_roles(GOVERNANCE_ROLES)),
):
    details = await document_details(db, doc_id)
    if not details:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return details


@router.patch("/docs/{doc_id}")
async def atualizar_governanca_documento(
    doc_id: str,
    payload: GovernanceMetadataPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(GOVERNANCE_ROLES)),
):
    doc = (
        await db.execute(
            select(KnowledgeDoc).where(
                KnowledgeDoc.id == doc_id,
                KnowledgeDoc.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    values = payload.model_dump(exclude_none=True)
    confirm_now = bool(values.pop("confirmar_fonte_agora", False))
    link_official = values.pop("link_official", None)

    if "authority_level" in values and values["authority_level"] not in AUTHORITY_LABELS:
        raise HTTPException(status_code=422, detail="Nível de autoridade inválido")
    if "legal_status" in values and values["legal_status"] not in LEGAL_STATUS_VALUES:
        raise HTTPException(status_code=422, detail="Situação jurídica inválida")

    extra = dict(doc.extra or {})
    extra.update(values)
    if "legal_status" in values:
        # PROVENIÊNCIA da vigência (review de segurança do PR #642): sem este
        # carimbo, `upsert_documento` não consegue distinguir a decisão do
        # curador da leitura automática do ingestor — e o re-feed periódico do
        # Planalto reverteria silenciosamente um diploma marcado 'revogada'
        # aqui. Ver ingestion_service.ORIGEM_VIGENCIA_CURADORIA.
        extra["legal_status_origem"] = f"{ORIGEM_VIGENCIA_CURADORIA}:{cu.id}"
        extra["legal_status_verificado_em"] = datetime.now(timezone.utc).isoformat()
        extra.pop("legal_status_inferido_em", None)
    if link_official is not None:
        extra["link_official"] = link_official
        if not doc.fonte and link_official:
            doc.fonte = link_official
    if confirm_now:
        extra["last_verified_at"] = datetime.now(timezone.utc).isoformat()
        extra["verified_by"] = str(cu.id)
    extra["governance_updated_at"] = datetime.now(timezone.utc).isoformat()
    extra["governance_updated_by"] = str(cu.id)
    # O listener ORM preserva rag_status=aprovado e confiança válida no flush.
    doc.extra = extra

    from app.models.audit_log import criar_audit_log

    role = getattr(cu.role, "value", str(cu.role))
    await criar_audit_log(
        db,
        user_id=cu.id,
        user_role=role,
        acao="UPDATE",
        entidade="knowledge_governance",
        registro_id=doc.id,
        detalhes=(
            f"Metadados jurídicos atualizados: {', '.join(sorted(values.keys())) or 'confirmação da fonte'}; "
            f"autoridade efetiva={inferir_autoridade_documento(doc)['code']}"
        ),
    )
    await db.commit()

    details = await document_details(db, doc_id)
    return {"detail": "Governança do documento atualizada", "documento": details}


class RevisaoRequest(BaseModel):
    aprovado: bool = Field(description="True para aprovar, False para rejeitar")


@router.post("/docs/{doc_id}/revisar")
async def revisar_documento_conhecimento(
    doc_id: str,
    payload: RevisaoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(GOVERNANCE_ROLES)),
):
    """Revisão manual de documento de conhecimento (G6).

    Marca documento como revisado (aprovado ou rejeitado). Documentos aprovados
    entram na base ativa do RAG; rejeitados ficam marcados mas são excluídos do
    retrieval por padrão.
    """
    doc = (
        await db.execute(
            select(KnowledgeDoc).where(
                KnowledgeDoc.id == doc_id,
                KnowledgeDoc.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    doc.revisado = payload.aprovado
    doc.revisado_por = str(cu.id)
    doc.revisado_em = datetime.now(timezone.utc)

    from app.models.audit_log import criar_audit_log

    role = getattr(cu.role, "value", str(cu.role))
    await criar_audit_log(
        db,
        user_id=cu.id,
        user_role=role,
        acao="REVISAO_CONHECIMENTO",
        entidade="knowledge_docs",
        registro_id=doc.id,
        detalhes=f"Documento {'aprovado' if payload.aprovado else 'rejeitado'} pelo revisor",
    )
    await db.commit()

    return {
        "detail": f"Documento {'aprovado' if payload.aprovado else 'rejeitado'}",
        "revisado": doc.revisado,
        "revisado_em": doc.revisado_em.isoformat() if doc.revisado_em else None,
    }


@router.post("/docs/{doc_id}/testar")
async def testar_conhecimento_documento(
    doc_id: str,
    payload: DocumentTestRequest,
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(require_roles(GOVERNANCE_ROLES)),
):
    result = await test_document_retrieval(
        db,
        doc_id,
        question=payload.pergunta,
        limit=payload.limite,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return result


@router.get("/docs/{doc_id}/comparar")
async def comparar_versoes_documento(
    doc_id: str,
    previous_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(require_roles(GOVERNANCE_ROLES)),
):
    result = await compare_versions(db, doc_id, previous_id=previous_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return result


@router.post("/testes-juridicos")
async def executar_testes_juridicos(
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(require_roles(GOVERNANCE_ROLES)),
):
    """Executa o conjunto permanente de smoke tests do retrieval jurídico."""
    return await run_legal_smoke_tests(db)
