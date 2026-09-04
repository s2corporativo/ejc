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

router = APIRouter(
    prefix="/rag/governanca",
    tags=["Base de Conhecimento — Governança"],
)
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
    retirar_quarentena: bool = False


class RevisaoRequest(BaseModel):
    aprovado: bool = Field(description="True para aprovar, False para rejeitar")
    # Notas OBRIGATÓRIAS: a tela sempre as exigiu e o próprio aviso do diálogo
    # promete que a decisão fica registrada "com estas notas" — mas o schema não
    # as declarava e o Pydantic as descartava em silêncio. O registro de
    # auditoria de uma decisão jurídica ficava sem a única parte que explica o
    # PORQUÊ (achado da revisão automatizada do PR, 03/09/2026).
    notas: str = Field(min_length=1, max_length=2000,
                       description="O que foi conferido e por que a decisão")
    # Confiança da curadoria aplicada NA MESMA transação da decisão. Antes a
    # tela fazia POST /revisar + PATCH /rag-curadoria: se o segundo falhasse, o
    # documento ficava aprovado sem nível de confiança e ninguém era avisado.
    confidence_level: Literal["alta", "media", "baixa"] | None = None


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deve_retirar_quarentena(
    extra_atual: dict | None,
    *,
    confirmar_fonte_agora: bool,
    retirar_explicito: bool,
) -> bool:
    """A confirmação contemporânea da fonte libera a quarentena sem aprovar.

    O frontend já possui a ação "Conferir fonte agora". Quando o documento está
    em quarentena, essa ação é suficiente para solicitar a retirada, mantendo o
    documento pendente de uma segunda decisão humana. A flag explícita continua
    disponível para clientes administrativos/API.
    """
    extra = dict(extra_atual or {})
    return bool(
        retirar_explicito
        or (confirmar_fonte_agora and extra.get("quarantine_active"))
    )


def _retirar_quarentena(
    extra_atual: dict | None,
    *,
    user_id: str,
    confirmar_fonte_agora: bool,
    agora: str | None = None,
) -> dict:
    """Retira quarentena sem aprovar o documento.

    A retirada exige uma confirmação contemporânea da fonte e sempre devolve o
    registro ao estado pendente, exigindo uma segunda ação explícita de revisão.
    """
    extra = dict(extra_atual or {})
    if not bool(extra.get("quarantine_active")):
        raise HTTPException(
            status_code=422,
            detail="Documento não está em quarentena ativa.",
        )
    if not confirmar_fonte_agora:
        raise HTTPException(
            status_code=422,
            detail=(
                "Para retirar a quarentena, confirme a fonte no mesmo PATCH "
                "com confirmar_fonte_agora=true."
            ),
        )
    timestamp = agora or _agora_iso()
    extra["quarantine_active"] = False
    extra["quarantine_released_at"] = timestamp
    extra["quarantine_released_by"] = str(user_id)
    extra["requires_human_review"] = True
    extra["human_reviewed"] = False
    extra["rag_status"] = "pendente"
    return extra


def _registrar_decisao_revisao(
    extra_atual: dict | None,
    *,
    aprovado: bool,
    user_id: str,
    agora: str | None = None,
    notas: str | None = None,
    confidence_level: str | None = None,
) -> dict:
    """Grava a decisão no mesmo contrato JSONB consumido pelo RAG/listener."""
    extra = dict(extra_atual or {})
    if aprovado and bool(extra.get("quarantine_active")):
        raise HTTPException(
            status_code=422,
            detail=(
                "Documento em quarentena não pode ser aprovado diretamente. "
                "Confirme a fonte e retire a quarentena antes da aprovação."
            ),
        )
    timestamp = agora or _agora_iso()
    extra["requires_human_review"] = True
    extra["human_reviewed"] = True
    extra["human_reviewed_at"] = timestamp
    extra["human_reviewed_by"] = str(user_id)
    extra["rag_status"] = "aprovado" if aprovado else "recusado"
    if notas is not None:
        extra["human_review_notes"] = str(notas)[:2000]
    if confidence_level is not None:
        # Mesmo contrato JSONB que o PATCH de curadoria escreve — aqui aplicado
        # na MESMA transação da decisão, para que não exista estado "aprovado
        # sem confiança".
        extra["confidence_level"] = confidence_level
        extra["curadoria"] = {
            "reviewed_by": str(user_id),
            "reviewed_at": timestamp,
            "notas": str(notas or "")[:2000],
        }
    return extra


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
    release_explicit = bool(values.pop("retirar_quarentena", False))
    link_official = values.pop("link_official", None)

    if (
        "authority_level" in values
        and values["authority_level"] not in AUTHORITY_LABELS
    ):
        raise HTTPException(status_code=422, detail="Nível de autoridade inválido")
    if "legal_status" in values and values["legal_status"] not in LEGAL_STATUS_VALUES:
        raise HTTPException(status_code=422, detail="Situação jurídica inválida")

    extra = dict(doc.extra or {})
    extra.update(values)
    timestamp = _agora_iso()

    if "legal_status" in values:
        extra["legal_status_origem"] = f"{ORIGEM_VIGENCIA_CURADORIA}:{cu.id}"
        extra["legal_status_verificado_em"] = timestamp
        extra.pop("legal_status_inferido_em", None)

    if link_official is not None:
        extra["link_official"] = link_official
        if not doc.fonte and link_official:
            doc.fonte = link_official

    if confirm_now:
        extra["last_verified_at"] = timestamp
        extra["verified_by"] = str(cu.id)

    release_quarantine = _deve_retirar_quarentena(
        extra,
        confirmar_fonte_agora=confirm_now,
        retirar_explicito=release_explicit,
    )
    if release_quarantine:
        extra = _retirar_quarentena(
            extra,
            user_id=str(cu.id),
            confirmar_fonte_agora=confirm_now,
            agora=timestamp,
        )

    extra["governance_updated_at"] = timestamp
    extra["governance_updated_by"] = str(cu.id)
    doc.extra = extra

    from app.models.audit_log import criar_audit_log

    role = getattr(cu.role, "value", str(cu.role))
    alteracoes = list(values.keys())
    if link_official is not None:
        alteracoes.append("link_official")
    if confirm_now:
        alteracoes.append("confirmar_fonte_agora")
    if release_quarantine:
        alteracoes.append("retirar_quarentena")
    await criar_audit_log(
        db,
        user_id=cu.id,
        user_role=role,
        acao="UPDATE",
        entidade="knowledge_governance",
        registro_id=doc.id,
        detalhes=(
            f"Metadados jurídicos atualizados: "
            f"{', '.join(sorted(alteracoes)) or 'sem campos'}; "
            f"autoridade efetiva={inferir_autoridade_documento(doc)['code']}"
        ),
    )
    await db.commit()

    details = await document_details(db, doc_id)
    return {"detail": "Governança do documento atualizada", "documento": details}


@router.post("/docs/{doc_id}/revisar")
async def revisar_documento_conhecimento(
    doc_id: str,
    payload: RevisaoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(GOVERNANCE_ROLES)),
):
    """Registra aprovação ou rejeição humana no contrato operacional do RAG."""
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

    timestamp = _agora_iso()
    doc.extra = _registrar_decisao_revisao(
        doc.extra,
        aprovado=payload.aprovado,
        user_id=str(cu.id),
        agora=timestamp,
        notas=payload.notas,
        confidence_level=payload.confidence_level,
    )

    # Compatibilidade com o campo legado: True significa aprovado; a decisão
    # completa (inclusive rejeição) fica registrada no JSONB operacional acima.
    doc.revisado = payload.aprovado
    doc.revisado_por = str(cu.id)
    doc.revisado_em = datetime.fromisoformat(timestamp)

    from app.models.audit_log import criar_audit_log

    role = getattr(cu.role, "value", str(cu.role))
    await criar_audit_log(
        db,
        user_id=cu.id,
        user_role=role,
        acao="REVISAO_CONHECIMENTO",
        entidade="knowledge_docs",
        registro_id=doc.id,
        detalhes=(
            f"Documento {'aprovado' if payload.aprovado else 'rejeitado'} pelo revisor; "
            f"rag_status={doc.extra.get('rag_status')}"
            + (f"; confidence_level={payload.confidence_level}"
               if payload.confidence_level else "")
            + f"; notas={payload.notas[:500]}"
        ),
    )
    await db.commit()

    return {
        "detail": f"Documento {'aprovado' if payload.aprovado else 'rejeitado'}",
        "revisado": doc.revisado,
        "rag_status": (doc.extra or {}).get("rag_status"),
        "human_reviewed": bool((doc.extra or {}).get("human_reviewed")),
        "confidence_level": (doc.extra or {}).get("confidence_level"),
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
