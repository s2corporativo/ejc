"""Vínculo de documentos existentes ao caso com efeitos de domínio preservados."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import is_gestao, role_str, verificar_acesso_caso
from app.core.security import ROLE_LEVEL
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.document import Document, DocConfidencialidade
from app.models.legal_doc import LegalDoc
from app.models.user import User
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
        await verificar_acesso_caso(db, cu, doc.case_id)
        return
    if is_gestao(cu) or doc.uploaded_by == cu.id:
        return
    if doc.client_id and target_case.client_id and doc.client_id == target_case.client_id:
        # O acesso ao target_case já foi provado; documento solto do mesmo
        # cliente é visível no GED aos responsáveis pelos casos desse cliente.
        return
    raise HTTPException(status_code=403, detail="Sem permissão para este documento")


async def buscar_documentos_vinculaveis(
    db: AsyncSession,
    cu: User,
    case_id: str,
    *,
    search: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Busca server-side somente documentos visíveis e ainda fora do caso."""
    await verificar_acesso_caso(db, cu, case_id)
    page = max(1, int(page or 1))
    page_size = min(50, max(1, int(page_size or 20)))

    q = select(Document).where(
        Document.deleted_at.is_(None),
        or_(Document.case_id.is_(None), Document.case_id != case_id),
    )

    if ROLE_LEVEL.get(role_str(cu), 0) < ROLE_LEVEL["socio"]:
        q = q.where(Document.confidencialidade.in_(list(_COFRE_EQUIPE)))

    if not is_gestao(cu):
        casos_visiveis = select(Case.id).where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            ),
        )
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
                Document.case_id.in_(casos_visiveis),
                (
                    Document.case_id.is_(None)
                    & Document.client_id.in_(clientes_visiveis)
                ),
                (
                    Document.case_id.is_(None)
                    & Document.client_id.is_(None)
                    & (Document.uploaded_by == cu.id)
                ),
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


async def vincular_documento_existente(
    db: AsyncSession,
    cu: User,
    case_id: str,
    document_id: str,
) -> dict:
    """Move/vincula documento ao caso e aplica efeitos de domínio atomicamente."""
    target_case = await verificar_acesso_caso(db, cu, case_id)
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
        return {"ok": True, "alterado": False, "document_id": doc.id, "case_id": case_id}

    ref = (
        await db.execute(
            select(LegalDoc.id, LegalDoc.titulo)
            .where(
                LegalDoc.protocolo_comprovante_doc_id == document_id,
                LegalDoc.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).first()
    if ref:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Documento é comprovante de protocolo da peça '{ref.titulo}' "
                "e não pode ser movido de caso. Atualize o comprovante na peça antes."
            ),
        )

    if doc.client_id and target_case.client_id and doc.client_id != target_case.client_id:
        raise HTTPException(
            status_code=400,
            detail="Caso pertence a outro cliente — vínculo negado",
        )

    origem_case_id = doc.case_id
    doc.case_id = case_id
    if not doc.client_id and target_case.client_id:
        doc.client_id = target_case.client_id

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
            "case_id_origem": origem_case_id,
            "case_id_destino": case_id,
            "status_caso_avancou": avancou,
        },
    )
    await db.commit()
    return {
        "ok": True,
        "alterado": True,
        "document_id": doc.id,
        "case_id": case_id,
        "status_caso_avancou": avancou,
    }
