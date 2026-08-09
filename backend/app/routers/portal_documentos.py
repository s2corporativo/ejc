# ── app/routers/portal_documentos.py ─────────────────────────────────────────
# Portal do Cliente — solicitações/upload e publicação explícita pelo escritório.
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.document import DocConfidencialidade, Document
from app.models.solicitacao_documento import (
    SolicitacaoDocumento,
    SolicitacaoDocumentoItem,
)
from app.models.user import User, UserRole
from app.routers.documents import EXTENSOES_PERMITIDAS, _validar_conteudo
from app.services.solicitacao_documento_service import recalcular_status

settings = get_settings()
logger = logging.getLogger("ejc.portal_documentos")
router = APIRouter(prefix="/portal", tags=["Portal do Cliente"])


def _exigir_cliente(cu: User) -> str:
    if cu.role != UserRole.cliente_externo or not cu.client_id:
        raise HTTPException(
            status_code=403, detail="Acesso exclusivo do Portal do Cliente"
        )
    return cu.client_id


def _exigir_advogado(cu: User) -> None:
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(
            status_code=403,
            detail="Publicação no Portal é restrita a advogado/sócio/administração",
        )


async def _documento_autorizado_staff(
    db: AsyncSession, cu: User, document_id: str
) -> Document:
    """Carrega o documento e reaplica ownership antes de publicar externamente."""
    _exigir_advogado(cu)
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if not doc.client_id:
        raise HTTPException(
            status_code=422,
            detail="Documento sem cliente vinculado não pode ser publicado no Portal",
        )

    if doc.case_id:
        from app.core.ownership import verificar_acesso_caso

        await verificar_acesso_caso(db, cu, doc.case_id)
    else:
        from app.core.client_ownership import obter_cliente_autorizado

        await obter_cliente_autorizado(db, cu, doc.client_id)
    return doc


@router.post("/admin/documentos/{document_id}/publicar")
async def publicar_documento_portal(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Publica explicitamente documento NORMAL para o próprio cliente.

    Confidencialidade e compartilhamento são dimensões independentes. Documentos
    interno/restrito/confidencial/segredo nunca são publicáveis por este endpoint.
    """
    doc = await _documento_autorizado_staff(db, cu, document_id)
    conf = getattr(doc.confidencialidade, "value", doc.confidencialidade)
    if conf != DocConfidencialidade.normal.value:
        raise HTTPException(
            status_code=422,
            detail=(
                "Somente documento com confidencialidade 'normal' pode ser "
                "publicado no Portal. Reclassifique conscientemente antes."
            ),
        )
    if doc.publicado_portal:
        return {
            "id": doc.id,
            "publicado_portal": True,
            "publicado_em": doc.publicado_em,
            "detail": "Documento já estava publicado no Portal",
        }

    agora = datetime.now(timezone.utc)
    doc.publicado_portal = True
    doc.publicado_em = agora
    doc.publicado_por = cu.id
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "PORTAL_PUBLICAR",
        "documents",
        doc.id,
        dados_depois={
            "client_id": doc.client_id,
            "case_id": doc.case_id,
            "publicado_portal": True,
            "publicado_em": agora.isoformat(),
        },
    )
    await db.commit()
    return {
        "id": doc.id,
        "publicado_portal": True,
        "publicado_em": agora,
        "detail": "Documento publicado no Portal do Cliente",
    }


@router.post("/admin/documentos/{document_id}/revogar")
async def revogar_documento_portal(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    doc = await _documento_autorizado_staff(db, cu, document_id)
    if not doc.publicado_portal:
        return {
            "id": doc.id,
            "publicado_portal": False,
            "detail": "Documento já não estava publicado no Portal",
        }

    antes = {
        "publicado_portal": True,
        "publicado_em": doc.publicado_em.isoformat() if doc.publicado_em else None,
        "publicado_por": doc.publicado_por,
    }
    doc.publicado_portal = False
    doc.publicado_em = None
    doc.publicado_por = None
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "PORTAL_REVOGAR",
        "documents",
        doc.id,
        dados_antes=antes,
        dados_depois={"publicado_portal": False},
    )
    await db.commit()
    return {
        "id": doc.id,
        "publicado_portal": False,
        "detail": "Acesso do documento pelo Portal revogado",
    }


@router.get(
    "/solicitacoes-documentos",
    dependencies=[Depends(rate_limit("portal-solicitacoes-listar", 60))],
)
async def listar_solicitacoes_portal(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    sols = (
        await db.execute(
            select(SolicitacaoDocumento, Case.titulo, Case.numero_interno)
            .join(Case, Case.id == SolicitacaoDocumento.case_id)
            .where(
                SolicitacaoDocumento.client_id == client_id,
                SolicitacaoDocumento.deleted_at.is_(None),
            )
            .order_by(SolicitacaoDocumento.created_at.desc())
        )
    ).all()

    itens_por_sol: dict[str, list] = {}
    if sols:
        todos_itens = (
            await db.execute(
                select(SolicitacaoDocumentoItem, Document.filename)
                .outerjoin(
                    Document, Document.id == SolicitacaoDocumentoItem.documento_id
                )
                .where(
                    SolicitacaoDocumentoItem.solicitacao_id.in_(
                        [s.id for s, _, _ in sols]
                    )
                )
                .order_by(SolicitacaoDocumentoItem.created_at)
            )
        ).all()
        for item, filename in todos_itens:
            itens_por_sol.setdefault(item.solicitacao_id, []).append((item, filename))

    return {
        "data": [
            {
                "id": sol.id,
                "case_id": sol.case_id,
                "caso_titulo": caso_titulo,
                "numero_interno": numero_interno,
                "mensagem": sol.mensagem,
                "created_at": sol.created_at,
                "status": sol.status,
                "itens": [
                    {
                        "id": item.id,
                        "nome": item.nome,
                        "descricao": item.descricao,
                        "status": item.status,
                        "enviado_em": item.enviado_em,
                        "filename": filename,
                    }
                    for item, filename in itens_por_sol.get(sol.id, [])
                ],
            }
            for sol, caso_titulo, numero_interno in sols
        ]
    }


@router.post(
    "/solicitacoes-documentos/itens/{item_id}/upload",
    status_code=201,
    dependencies=[Depends(rate_limit("portal-solicitacoes-upload", 20))],
)
async def upload_item_solicitacao(
    item_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    row = (
        await db.execute(
            select(SolicitacaoDocumentoItem, SolicitacaoDocumento)
            .join(
                SolicitacaoDocumento,
                SolicitacaoDocumento.id == SolicitacaoDocumentoItem.solicitacao_id,
            )
            .where(
                SolicitacaoDocumentoItem.id == item_id,
                SolicitacaoDocumento.client_id == client_id,
                SolicitacaoDocumento.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    item, sol = row
    if item.status != "pendente":
        raise HTTPException(status_code=422, detail="Este documento já foi enviado")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in EXTENSOES_PERMITIDAS:
        raise HTTPException(status_code=422, detail=f"Extensão não permitida: {ext}")
    conteudo = await file.read()
    if len(conteudo) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail=f"Arquivo excede {settings.MAX_UPLOAD_MB}MB"
        )
    mime_real = _validar_conteudo(ext, conteudo)

    agora = datetime.now(timezone.utc)
    doc_id = str(uuid4())
    claim = await db.execute(
        update(SolicitacaoDocumentoItem)
        .where(
            SolicitacaoDocumentoItem.id == item.id,
            SolicitacaoDocumentoItem.status == "pendente",
        )
        .values(status="enviado", enviado_em=agora, documento_id=doc_id)
    )
    if claim.rowcount == 0:
        raise HTTPException(status_code=422, detail="Este documento já foi enviado")

    subdir = f"{agora.year}/{agora.month:02d}"
    os.makedirs(f"{settings.UPLOAD_DIR}/{subdir}", exist_ok=True)
    filepath = f"{subdir}/{doc_id}{ext}"
    async with aiofiles.open(f"{settings.UPLOAD_DIR}/{filepath}", "wb") as destino:
        await destino.write(conteudo)

    nome_arquivo = (file.filename or f"documento{ext}")[:255]
    doc = Document(
        id=doc_id,
        titulo=item.nome[:255],
        tipo="outro",
        filename=nome_arquivo,
        filepath=filepath,
        mimetype=mime_real,
        size_bytes=len(conteudo),
        confidencialidade=DocConfidencialidade.normal,
        # Upload feito pelo próprio titular já é, por definição, conhecido por
        # ele. Marcamos publicação explícita para que continue visível no Portal.
        publicado_portal=True,
        publicado_em=agora,
        publicado_por=cu.id,
        case_id=sol.case_id,
        client_id=sol.client_id,
        uploaded_by=cu.id,
    )
    db.add(doc)

    demais = (
        await db.execute(
            select(SolicitacaoDocumentoItem.id, SolicitacaoDocumentoItem.status).where(
                SolicitacaoDocumentoItem.solicitacao_id == sol.id
            )
        )
    ).all()
    status_itens = [
        "enviado" if outro_id == item.id else outro_status
        for outro_id, outro_status in demais
    ]
    sol.status = recalcular_status(status_itens)

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPLOAD",
        "solicitacao_documento_itens",
        item.id,
        detalhes=(
            f"portal: item '{item.nome}' da solicitação {sol.id} → documento {doc_id}"
        ),
        dados_depois={
            "documento_id": doc_id,
            "publicado_portal": True,
            "origem": "upload_cliente",
        },
    )
    await db.commit()

    try:
        from app.services.notification_service import notificar

        case = (
            await db.execute(select(Case).where(Case.id == sol.case_id))
        ).scalar_one_or_none()
        if case and case.advogado_responsavel_id:
            ref = case.numero_interno or case.titulo or sol.case_id
            await notificar(
                db,
                case.advogado_responsavel_id,
                "Documento recebido do cliente",
                f"O cliente enviou o documento '{item.nome}' solicitado no caso "
                f"{ref} (solicitação {sol.status}).",
                tipo="documento",
                link=f"/casos/{sol.case_id}",
                forcar_sino=True,
            )
    except Exception as exc:
        logger.warning(
            "[PortalDoc] notificação ao advogado falhou (item %s): %s",
            item.id,
            exc,
        )

    return {
        "id": item.id,
        "status": sol.status,
        "item_status": item.status,
        "documento_id": doc_id,
        "filename": nome_arquivo,
        "publicado_portal": True,
    }
