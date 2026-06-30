# ── app/routers/signatures.py ────────────────────────────────────────────────
# Assinatura eletrônica simples (MP 2.200-2/2001 art. 10 §2º):
# manifestação de aceite + hash SHA-256 do arquivo + IP + UA + timestamp,
# tudo em trilha de auditoria. Procuração ad judicia não exige forma
# especial (CPC art. 105) — adequado para procurações e contratos.
from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User, UserRole
from app.models.document import Document
from app.models.signature import SignatureRequest, SignatureStatus
from app.models.notification import Notification
from app.models.audit_log import criar_audit_log

router = APIRouter(prefix="/signatures", tags=["Assinatura Eletrônica"])


class CriarSolicitacaoReq(BaseModel):
    document_id: str
    client_id: str


@router.post("/", status_code=201)
async def criar_solicitacao(
    payload: CriarSolicitacaoReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio", "advogado"])),
):
    """Advogado solicita assinatura do cliente sobre um documento do GED."""
    doc = (await db.execute(select(Document).where(
        Document.id == payload.document_id, Document.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Hash do arquivo no momento da solicitação (integridade)
    from app.core.config import get_settings as _gs
    full_path = f"{_gs().UPLOAD_DIR}/{doc.filepath}"
    try:
        with open(full_path, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Arquivo físico ausente")

    sr = SignatureRequest(
        id=str(uuid4()), document_id=doc.id, client_id=payload.client_id,
        hash_sha256=h, criado_por=cu.id,
    )
    db.add(sr)

    # Notificar o(s) login(s) do portal deste cliente
    portais = (await db.execute(select(User).where(
        User.client_id == payload.client_id,
        User.role == UserRole.cliente_externo,
        User.is_active == True,
    ))).scalars().all()
    for p in portais:
        db.add(Notification(
            id=str(uuid4()), user_id=p.id,
            titulo="✍️ Documento aguardando sua assinatura",
            mensagem=doc.titulo, tipo="assinatura", link="/portal/assinaturas",
        ))

    await criar_audit_log(db, cu.id, cu.role.value, "CREATE",
                          "signature_requests", sr.id,
                          detalhes=f"Doc: {doc.titulo}")
    await db.commit()
    return {"id": sr.id, "hash": h, "detail": "Solicitação criada"}


@router.get("/")
async def listar(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Staff: todas. Cliente do portal: apenas as suas (pendentes primeiro)."""
    q = select(SignatureRequest).where(SignatureRequest.deleted_at.is_(None))
    if cu.role == UserRole.cliente_externo:
        q = q.where(SignatureRequest.client_id == cu.client_id)
    rows = (await db.execute(
        q.order_by(SignatureRequest.status, SignatureRequest.created_at.desc())
    )).scalars().all()

    # Anexar título do documento
    out = []
    for s in rows:
        doc = (await db.execute(select(Document).where(
            Document.id == s.document_id
        ))).scalar_one_or_none()
        out.append({
            "id": s.id, "document_id": s.document_id,
            "documento": doc.titulo if doc else "—",
            "status": s.status.value, "hash": s.hash_sha256[:16] + "…",
            "assinado_em": s.assinado_em, "created_at": s.created_at,
        })
    return {"data": out}


@router.post("/{sig_id}/assinar")
async def assinar(
    sig_id: str, request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Cliente (portal) registra o aceite. Evidências gravadas:
    identificação (login autenticado), hash do arquivo, IP, UA, timestamp.
    """
    if cu.role != UserRole.cliente_externo:
        raise HTTPException(status_code=403,
                            detail="Apenas o cliente assina pelo Portal")
    sr = (await db.execute(select(SignatureRequest).where(
        SignatureRequest.id == sig_id,
        SignatureRequest.client_id == cu.client_id,   # isolamento
        SignatureRequest.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if sr.status != SignatureStatus.pendente:
        raise HTTPException(status_code=409, detail="Já processada")

    sr.status = SignatureStatus.assinado
    sr.assinado_em = datetime.now(timezone.utc)
    sr.assinado_por_user = cu.id
    sr.ip = request.client.host if request.client else None
    sr.user_agent = (request.headers.get("user-agent") or "")[:300]

    await criar_audit_log(
        db, cu.id, cu.role.value, "ASSINATURA", "signature_requests", sig_id,
        detalhes=f"hash={sr.hash_sha256[:16]} ip={sr.ip}",
        ip=sr.ip,
    )
    await db.commit()
    return {"detail": "Documento assinado com sucesso",
            "comprovante": {
                "assinado_em": sr.assinado_em.isoformat(),
                "hash_documento": sr.hash_sha256,
                "ip": sr.ip,
            }}
