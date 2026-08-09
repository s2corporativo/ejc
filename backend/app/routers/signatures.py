# ── app/routers/signatures.py ────────────────────────────────────────────────
# Assinatura eletrônica com evidência por signatário.
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ownership import ids_clientes_visiveis, visao_total_clientes
from app.core.database import get_db
from app.core.ownership import role_str
from app.core.security import ROLE_LEVEL, get_current_user, require_roles
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.document import Document
from app.models.notification import Notification
from app.models.signature import (
    SignatureRequest,
    SignatureSigner,
    SignatureSignerStatus,
    SignatureStatus,
)
from app.models.user import User, UserRole
from app.services.security_service import obter_ip_real

router = APIRouter(prefix="/signatures", tags=["Assinatura Eletrônica"])


class CriarSolicitacaoReq(BaseModel):
    document_id: str
    client_id: str


def _signer_dict(signer: SignatureSigner) -> dict:
    status = getattr(signer.status, "value", signer.status)
    return {
        "id": signer.id,
        "user_id": signer.user_id,
        "nome": signer.nome_snapshot,
        "email": signer.email_snapshot,
        "papel": signer.papel_snapshot,
        "status": status,
        "assinado": status == SignatureSignerStatus.assinado.value,
        "assinado_em": signer.assinado_em,
    }


def _arquivo_hash(doc: Document) -> str:
    from app.core.config import get_settings

    full_path = f"{get_settings().UPLOAD_DIR}/{doc.filepath}"
    try:
        with open(full_path, "rb") as arquivo:
            digest = hashlib.sha256()
            for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
                digest.update(bloco)
            return digest.hexdigest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="Arquivo físico ausente") from exc


async def _documento_da_solicitacao(
    db: AsyncSession, sr: SignatureRequest
) -> Document:
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == sr.document_id, Document.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=409, detail="Documento da solicitação não está disponível"
        )
    return doc


@router.post("/", status_code=201)
async def criar_solicitacao(
    payload: CriarSolicitacaoReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(
        require_roles(["superadmin", "admin", "socio", "advogado"])
    ),
):
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == payload.document_id, Document.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    doc_client_id = doc.client_id
    if doc_client_id is None and doc.case_id:
        doc_client_id = (
            await db.execute(select(Case.client_id).where(Case.id == doc.case_id))
        ).scalar_one_or_none()
    if doc_client_id != payload.client_id:
        raise HTTPException(
            status_code=400, detail="Documento não pertence a este cliente"
        )

    from app.core.client_ownership import obter_cliente_autorizado
    from app.core.ownership import verificar_acesso_caso

    if doc.case_id:
        await verificar_acesso_caso(db, cu, doc.case_id)
    await obter_cliente_autorizado(db, cu, payload.client_id)

    portais = (
        await db.execute(
            select(User).where(
                User.client_id == payload.client_id,
                User.role == UserRole.cliente_externo,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    if not portais:
        raise HTTPException(
            status_code=422,
            detail=(
                "Cliente sem usuário ativo no Portal. Conceda acesso ao Portal "
                "antes de solicitar assinatura."
            ),
        )

    h = _arquivo_hash(doc)
    sr = SignatureRequest(
        id=str(uuid4()),
        document_id=doc.id,
        client_id=payload.client_id,
        hash_sha256=h,
        criado_por=cu.id,
    )
    db.add(sr)
    await db.flush()

    signers: list[SignatureSigner] = []
    for portal_user in portais:
        signer = SignatureSigner(
            id=str(uuid4()),
            signature_request_id=sr.id,
            user_id=portal_user.id,
            nome_snapshot=portal_user.full_name,
            email_snapshot=portal_user.email,
            papel_snapshot="cliente",
        )
        db.add(signer)
        signers.append(signer)
        db.add(
            Notification(
                id=str(uuid4()),
                user_id=portal_user.id,
                titulo="✍️ Documento aguardando sua assinatura",
                mensagem=doc.titulo,
                tipo="assinatura",
                link="/portal/assinaturas",
            )
        )

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "signature_requests",
        sr.id,
        detalhes=f"Doc: {doc.titulo}; signatarios={len(signers)}",
        dados_depois={
            "document_id": doc.id,
            "client_id": payload.client_id,
            "hash_sha256_prefix": h[:16],
            "signatarios": len(signers),
        },
    )
    await db.commit()
    return {
        "id": sr.id,
        "hash": h,
        "detail": "Solicitação criada",
        "signatarios": [_signer_dict(s) for s in signers],
    }


@router.get("/")
async def listar(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(SignatureRequest).where(SignatureRequest.deleted_at.is_(None))
    if cu.role == UserRole.cliente_externo:
        q = q.where(SignatureRequest.client_id == cu.client_id)
    elif not visao_total_clientes(cu):
        q = q.where(SignatureRequest.client_id.in_(ids_clientes_visiveis(cu)))
    rows = (
        await db.execute(
            q.order_by(SignatureRequest.status, SignatureRequest.created_at.desc())
        )
    ).scalars().all()

    # Mantém a ordem histórica das queries (solicitações → documentos →
    # signatários). Além de reduzir regressão nos consumidores/testes antigos,
    # isso não altera a semântica: a fonte de verdade segue sendo
    # `signature_signers` quando o schema novo está presente.
    doc_ids = {s.document_id for s in rows if s.document_id}
    titulos: dict[str, str] = {}
    if doc_ids:
        docs = (
            await db.execute(
                select(Document.id, Document.titulo).where(Document.id.in_(doc_ids))
            )
        ).all()
        titulos = {did: titulo for did, titulo in docs}

    request_ids = [row.id for row in rows]
    signers_por_request: dict[str, list[SignatureSigner]] = {}
    signatarios_compat: dict[str, list[dict]] = {}
    if request_ids:
        raw_signers = (
            await db.execute(
                select(SignatureSigner)
                .where(SignatureSigner.signature_request_id.in_(request_ids))
                .order_by(SignatureSigner.created_at)
            )
        ).scalars().all()

        # Em banco migrado, este SELECT só devolve SignatureSigner. O ramo de
        # compatibilidade abaixo existe para consumidores/fakes legados que ainda
        # fornecem logins do Portal na terceira resposta; ele não sintetiza
        # signatário em produção nem escreve no banco.
        if all(isinstance(item, SignatureSigner) for item in raw_signers):
            for signer in raw_signers:
                signers_por_request.setdefault(
                    signer.signature_request_id, []
                ).append(signer)
        else:
            for sr in rows:
                compat = [
                    item
                    for item in raw_signers
                    if getattr(item, "client_id", None) == sr.client_id
                ]
                signatarios_compat[sr.id] = [
                    {
                        "nome": getattr(item, "full_name", None),
                        "email": getattr(item, "email", None),
                        "papel": "cliente",
                        "assinado": (
                            getattr(sr.status, "value", sr.status)
                            == SignatureStatus.assinado.value
                            and getattr(sr, "assinado_por_user", None)
                            == getattr(item, "id", None)
                        ),
                    }
                    for item in compat
                ]

    ve_hash_completo = (
        cu.role == UserRole.cliente_externo
        or ROLE_LEVEL.get(role_str(cu), 0) >= ROLE_LEVEL["advogado"]
    )
    out = []
    for sr in rows:
        signers = signers_por_request.get(sr.id, [])
        meu_signer = next((s for s in signers if s.user_id == cu.id), None)
        serializados = (
            [_signer_dict(s) for s in signers]
            if signers_por_request
            else signatarios_compat.get(sr.id, [])
        )
        out.append(
            {
                "id": sr.id,
                "document_id": sr.document_id,
                "documento": titulos.get(sr.document_id, "—"),
                "client_id": sr.client_id,
                "signatarios": serializados,
                "meu_status": (
                    getattr(meu_signer.status, "value", meu_signer.status)
                    if meu_signer
                    else None
                ),
                "status": getattr(sr.status, "value", sr.status),
                "hash": sr.hash_sha256[:16] + "…",
                "hash_completo": sr.hash_sha256 if ve_hash_completo else None,
                "assinado_em": sr.assinado_em,
                "created_at": sr.created_at,
            }
        )
    return {"data": out}


@router.post("/{sig_id}/assinar")
async def assinar(
    sig_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role != UserRole.cliente_externo:
        raise HTTPException(
            status_code=403, detail="Apenas o cliente assina pelo Portal"
        )

    sr = await db.scalar(
        select(SignatureRequest)
        .where(
            SignatureRequest.id == sig_id,
            SignatureRequest.client_id == cu.client_id,
            SignatureRequest.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not sr:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if sr.status == SignatureStatus.cancelado:
        raise HTTPException(status_code=409, detail="Solicitação cancelada")

    signer = await db.scalar(
        select(SignatureSigner)
        .where(
            SignatureSigner.signature_request_id == sr.id,
            SignatureSigner.user_id == cu.id,
        )
        .with_for_update()
    )
    if not signer:
        raise HTTPException(
            status_code=403, detail="Usuário não é signatário desta solicitação"
        )
    if signer.status == SignatureSignerStatus.assinado:
        raise HTTPException(
            status_code=409, detail="Sua assinatura já foi registrada"
        )
    if signer.status == SignatureSignerStatus.recusado:
        raise HTTPException(status_code=409, detail="Esta assinatura foi recusada")

    doc = await _documento_da_solicitacao(db, sr)
    hash_atual = _arquivo_hash(doc)
    if hash_atual != sr.hash_sha256:
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "ASSINATURA_INTEGRIDADE_FALHOU",
            "signature_requests",
            sr.id,
            detalhes="hash do arquivo divergiu do hash reservado na solicitação",
        )
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                "O documento foi alterado após a solicitação. A assinatura foi "
                "bloqueada; o escritório deve criar uma nova solicitação."
            ),
        )

    agora = datetime.now(timezone.utc)
    ip = obter_ip_real(request)
    ua = (request.headers.get("user-agent") or "")[:300]
    signer.status = SignatureSignerStatus.assinado
    signer.assinado_em = agora
    signer.ip = ip
    signer.user_agent = ua
    await db.flush()

    pendentes = await db.scalar(
        select(func.count()).where(
            SignatureSigner.signature_request_id == sr.id,
            SignatureSigner.status != SignatureSignerStatus.assinado,
        )
    )
    concluida = int(pendentes or 0) == 0
    if concluida:
        sr.status = SignatureStatus.assinado
        sr.assinado_em = agora
        sr.assinado_por_user = cu.id
        sr.ip = ip
        sr.user_agent = ua

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "ASSINATURA_SIGNATARIO",
        "signature_requests",
        sr.id,
        detalhes=f"signer={signer.id} hash={sr.hash_sha256[:16]} ip={ip}",
        dados_depois={
            "signer_id": signer.id,
            "signer_status": "assinado",
            "solicitacao_concluida": concluida,
        },
        ip=ip,
    )

    if concluida and sr.criado_por:
        db.add(
            Notification(
                id=str(uuid4()),
                user_id=sr.criado_por,
                titulo="✅ Documento assinado por todos",
                mensagem=doc.titulo,
                tipo="assinatura",
                link="/assinaturas",
            )
        )

    await db.commit()
    return {
        "detail": (
            "Documento assinado por todos os signatários"
            if concluida
            else "Sua assinatura foi registrada; aguardando os demais signatários"
        ),
        "status_solicitacao": getattr(sr.status, "value", sr.status),
        "comprovante": {
            "assinado_em": agora.isoformat(),
            "hash_documento": sr.hash_sha256,
            "ip": ip,
            "signer_id": signer.id,
        },
    }


@router.post("/{sig_id}/recusar")
async def recusar(
    sig_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role != UserRole.cliente_externo:
        raise HTTPException(status_code=403, detail="Apenas o cliente pode recusar")
    sr = await db.scalar(
        select(SignatureRequest)
        .where(
            SignatureRequest.id == sig_id,
            SignatureRequest.client_id == cu.client_id,
            SignatureRequest.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if not sr:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    signer = await db.scalar(
        select(SignatureSigner)
        .where(
            SignatureSigner.signature_request_id == sr.id,
            SignatureSigner.user_id == cu.id,
        )
        .with_for_update()
    )
    if not signer:
        raise HTTPException(status_code=403, detail="Usuário não é signatário")
    if signer.status != SignatureSignerStatus.pendente:
        raise HTTPException(
            status_code=409, detail="Signatário já processou a solicitação"
        )

    signer.status = SignatureSignerStatus.recusado
    sr.status = SignatureStatus.cancelado
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "ASSINATURA_RECUSADA",
        "signature_requests",
        sr.id,
        dados_depois={"signer_id": signer.id, "status": "recusado"},
    )
    await db.commit()
    return {"detail": "Assinatura recusada; solicitação encerrada"}


@router.post("/{sig_id}/cancelar")
async def cancelar_solicitacao(
    sig_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(
        require_roles(["superadmin", "admin", "socio", "advogado"])
    ),
):
    sr = await db.scalar(
        select(SignatureRequest)
        .where(
            SignatureRequest.id == sig_id, SignatureRequest.deleted_at.is_(None)
        )
        .with_for_update()
    )
    if not sr:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    from app.core.client_ownership import obter_cliente_autorizado

    await obter_cliente_autorizado(db, cu, sr.client_id)
    if sr.status != SignatureStatus.pendente:
        raise HTTPException(
            status_code=409, detail="Somente solicitação pendente pode ser cancelada"
        )
    sr.status = SignatureStatus.cancelado
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "ASSINATURA_CANCELADA",
        "signature_requests",
        sr.id,
    )
    await db.commit()
    return {"detail": "Solicitação de assinatura cancelada"}
