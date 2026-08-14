"""Vínculo de documentos existentes ao caso com efeitos de domínio preservados.

Regra de integridade: este fluxo vincula somente documento ainda sem caso. Um
arquivo já pertencente a outro caso é evidência daquele contexto e não é movido;
reuso entre casos exige cópia controlada em fluxo próprio, preservando cadeia
probatória, protocolo e referências de Prova.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import is_gestao, role_str, verificar_acesso_caso
from app.core.security import ROLE_LEVEL, requer_equipe_juridica
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.document import Document, DocConfidencialidade
from app.models.legal_doc import LegalDoc
from app.models.prova import Prova
from app.models.user import User
from app.services.document_reference_guard import (
    EscopoGuardaDocumento,
    exigir_documento_sem_referencias_bloqueantes,
)
from app.services.status_transicao import avancar_status_por_evento

_COFRE_EQUIPE = {DocConfidencialidade.normal, DocConfidencialidade.interno}


def _pode_ver_confidencialidade(cu: User, conf: DocConfidencialidade) -> bool:
    if role_str(cu) == "cliente_externo":
        return conf == DocConfidencialidade.normal
    if ROLE_LEVEL.get(role_str(cu), 0) >= ROLE_LEVEL["socio"]:
        return True
    return conf in _COFRE_EQUIPE


async def _gate_documento_origem(
    db: AsyncSession, cu: User, doc: Document, target_case: Case
) -> None:
    """Replica o escopo efetivo do GED sem depender de router."""
    if not _pode_ver_confidencialidade(cu, doc.confidencialidade):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")

    if doc.case_id:
        # Não vaza existência de documento de caso alheio: primeiro prova acesso
        # à origem; o bloqueio de movimento é aplicado depois.
        await verificar_acesso_caso(db, cu, doc.case_id)
        return
    if is_gestao(cu) or doc.uploaded_by == cu.id:
        return
    if doc.client_id and target_case.client_id and doc.client_id == target_case.client_id:
        # O acesso ao target_case já foi provado; documento solto do mesmo
        # cliente é visível no GED aos responsáveis pelos casos desse cliente.
        return
    raise HTTPException(status_code=403, detail="Sem permissão para este documento")


def _ref_protocolo_ativo(document_id_col):
    """Predicado SQL de elegibilidade, aplicado antes de count/offset/limit."""
    return (
        select(LegalDoc.id)
        .where(
            LegalDoc.protocolo_comprovante_doc_id == document_id_col,
            LegalDoc.deleted_at.is_(None),
        )
        .exists()
    )


def _ref_prova_ativa(document_id_col):
    """Predicado SQL de elegibilidade, aplicado antes de count/offset/limit."""
    return (
        select(Prova.id)
        .where(
            Prova.document_id == document_id_col,
            Prova.deleted_at.is_(None),
        )
        .exists()
    )


async def buscar_documentos_vinculaveis(
    db: AsyncSession,
    cu: User,
    case_id: str,
    *,
    search: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Busca server-side apenas documentos realmente vinculáveis ao caso.

    A elegibilidade é aplicada antes de count/offset/limit: documento de outro
    caso, outro cliente, usado como comprovante de protocolo ou referenciado por
    Prova ativa não ocupa a página nem gera ação que falhará deterministicamente.
    """
    requer_equipe_juridica(cu, "Vínculo documental restrito à equipe jurídica")
    target_case = await verificar_acesso_caso(db, cu, case_id)
    page = max(1, int(page or 1))
    page_size = min(50, max(1, int(page_size or 20)))

    # Caso já vinculado é imutável por este fluxo. Isso preserva Prova,
    # protocolo, ownership e histórico do caso de origem.
    q = select(Document).where(
        Document.deleted_at.is_(None),
        Document.case_id.is_(None),
        ~_ref_protocolo_ativo(Document.id),
        ~_ref_prova_ativa(Document.id),
    )

    # Tenant do destino é requisito de elegibilidade antes da paginação.
    # Documento sem client_id pode ser adotado pelo caso se o usuário tiver o
    # gate de origem; documento explicitamente pertencente a outro cliente não.
    if target_case.client_id:
        q = q.where(
            or_(
                Document.client_id.is_(None),
                Document.client_id == target_case.client_id,
            )
        )
    else:
        q = q.where(Document.client_id.is_(None))

    if ROLE_LEVEL.get(role_str(cu), 0) < ROLE_LEVEL["socio"]:
        q = q.where(Document.confidencialidade.in_(list(_COFRE_EQUIPE)))

    if not is_gestao(cu):
        clientes_visiveis = select(Case.client_id).where(
            Case.deleted_at.is_(None),
            Case.client_id.is_not(None),
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            ),
        )
        q = q.where(
            or_(
                Document.client_id.in_(clientes_visiveis),
                (Document.client_id.is_(None) & (Document.uploaded_by == cu.id)),
            )
        )

    termo = (search or "").strip()
    if termo:
        q = q.where(
            or_(
                Document.titulo.ilike(f"%{termo}%"),
                Document.filename.ilike(f"%{termo}%"),
            )
        )

    total = (
        await db.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
    docs = (
        await db.execute(
            q.order_by(Document.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "data": [
            {
                "id": d.id,
                "titulo": d.titulo,
                "filename": d.filename,
                "case_id": d.case_id,
                "confidencialidade": d.confidencialidade.value,
                "created_at": d.created_at,
            }
            for d in docs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def obter_ocr_documento_vinculado(
    db: AsyncSession,
    case_id: str,
    document_id: str,
) -> str | None:
    """Retorna OCR somente se o documento permanecer no caso recém-vinculado."""
    return (
        await db.execute(
            select(Document.ocr_text).where(
                Document.id == document_id,
                Document.case_id == case_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def vincular_documento_existente(
    db: AsyncSession,
    cu: User,
    case_id: str,
    document_id: str,
) -> dict:
    """Vincula documento solto ao caso e aplica efeitos de domínio atomicamente."""
    requer_equipe_juridica(cu, "Vínculo documental restrito à equipe jurídica")
    await verificar_acesso_caso(db, cu, case_id)

    # Operações com documentos diferentes no mesmo caso precisam serializar a
    # transição aberto→em_instrucao e seu CaseMovimento.
    target_case = (
        await db.execute(
            select(Case)
            .where(Case.id == case_id, Case.deleted_at.is_(None))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if target_case is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    doc = (
        await db.execute(
            select(Document)
            .where(Document.id == document_id, Document.deleted_at.is_(None))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    await _gate_documento_origem(db, cu, doc, target_case)
    if doc.case_id == case_id:
        return {
            "ok": True,
            "alterado": False,
            "document_id": doc.id,
            "case_id": case_id,
        }
    if doc.case_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "Documento já pertence a outro caso e não pode ser movido. "
                "Preserve a evidência original e use fluxo de cópia controlada para reuso."
            ),
        )

    # A política de referências vive fora do router e é compartilhável por
    # delete, Drive e demais portas do lifecycle. Para vínculo, preserva o
    # contrato F3.2 já homologado: protocolo e Prova são bloqueantes.
    await exigir_documento_sem_referencias_bloqueantes(
        db,
        document_id,
        acao="vinculado por este fluxo",
        escopo=EscopoGuardaDocumento.VINCULO,
    )

    if doc.client_id and doc.client_id != target_case.client_id:
        raise HTTPException(
            status_code=400,
            detail="Caso pertence a outro cliente — vínculo negado",
        )

    doc.case_id = case_id
    if not doc.client_id and target_case.client_id:
        doc.client_id = target_case.client_id

    # Mesmo invariante do upload direto: a primeira revisão é o próprio grupo.
    # Sem isso, uma versão 2 futura aponta para um grupo que a versão 1 não tem.
    if not doc.versao_grupo_id:
        doc.versao_grupo_id = doc.id

    avancou = await avancar_status_por_evento(
        db,
        target_case,
        "documento_vinculado",
        user_id=cu.id,
    )
    await criar_audit_log(
        db,
        cu.id,
        role_str(cu),
        "VINCULAR",
        "documents",
        document_id,
        dados_depois={
            "case_id_origem": None,
            "case_id_destino": case_id,
            "status_caso_avancou": avancou,
        },
    )
    await db.commit()
    return {
        "ok": True,
        "alterado": True,
        "document_id": document_id,
        "case_id": case_id,
        "status_caso_avancou": avancou,
    }
