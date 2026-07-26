# ── app/routers/signatures.py ────────────────────────────────────────────────
# Assinatura eletrônica simples (MP 2.200-2/2001 art. 10 §2º):
# manifestação de aceite + hash SHA-256 do arquivo + IP + UA + timestamp,
# tudo em trilha de auditoria. Procuração ad judicia não exige forma
# especial (CPC art. 105) — adequado para procurações e contratos.
from __future__ import annotations
import hashlib
import hmac
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ownership import ids_clientes_visiveis, visao_total_clientes
from app.core.database import get_db
from app.core.ownership import role_str
from app.core.security import ROLE_LEVEL, get_current_user, require_roles
from app.models.user import User, UserRole
from app.models.case import Case
from app.models.document import Document
from app.models.signature import SignatureRequest, SignatureStatus
from app.models.notification import Notification
from app.models.audit_log import criar_audit_log
from app.services.security_service import obter_ip_real

router = APIRouter(prefix="/signatures", tags=["Assinatura Eletrônica"])


class CriarSolicitacaoReq(BaseModel):
    document_id: str
    client_id: str


def _signatario(u: User, sr: SignatureRequest) -> dict:
    """Shape de um signatário (usuário do portal do cliente) esperado pelo
    frontend (Assinaturas.tsx): nome/email/papel + estado da assinatura."""
    return {
        "nome": u.full_name,
        "email": u.email,
        "papel": "cliente",
        "assinado": (sr.status == SignatureStatus.assinado
                     and sr.assinado_por_user == u.id),
    }


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

    # DOC-106/SYS-068: ownership do SOLICITANTE. require_roles garante o papel,
    # mas não que ESTE advogado tenha acesso ao documento/caso — sem isto, um
    # advogado de outra carteira que conheça os IDs iniciaria a assinatura.
    # Reusa o gate único do GED (case ownership OU acesso ao cliente).
    from app.routers.documents import _verificar_acesso_documento
    await _verificar_acesso_documento(db, cu, doc)

    # Valida que o documento pertence ao cliente (direto via doc.client_id ou pelo
    # caso vinculado) ANTES de notificar o portal — senão notifica-se o cliente
    # sobre um documento de OUTRO cliente (vazamento).
    doc_client_id = doc.client_id
    if doc_client_id is None and doc.case_id:
        doc_client_id = (await db.execute(
            select(Case.client_id).where(Case.id == doc.case_id)
        )).scalar_one_or_none()
    if doc_client_id != payload.client_id:
        raise HTTPException(status_code=400,
                            detail="Documento não pertence a este cliente")

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
                          detalhes=f"Doc: {doc.titulo}; visualizacao_requerida")
    await db.commit()
    # DOC-107/SYS-069: a visualização do documento é REQUERIDA antes do aceite.
    # O preview autenticado por solicitação é servido por GET
    # /signatures/{sig_id}/documento (abaixo). A comprovação PERSISTIDA de que o
    # cliente visualizou (flag `visualizado_em` no SignatureRequest) depende de
    # migration — de responsabilidade do outro agente; aqui apenas sinalizamos.
    # TODO(DOC-107): persistir visualizacao (coluna + gate no /assinar) quando a
    # migration existir; hoje registramos em audit log a exigência.
    return {"id": sr.id, "hash": h, "detail": "Solicitação criada",
            "visualizacao_requerida": True,
            "preview_url": f"/signatures/{sr.id}/documento",
            "signatarios": [_signatario(p, sr) for p in portais]}


@router.get("/")
async def listar(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Gestão/secretaria: todas. Demais staff: só as da própria carteira.
    Cliente do portal: apenas as suas (pendentes primeiro)."""
    q = select(SignatureRequest).where(SignatureRequest.deleted_at.is_(None))
    if cu.role == UserRole.cliente_externo:
        q = q.where(SignatureRequest.client_id == cu.client_id)
    elif not visao_total_clientes(cu):
        # Pente fino 2026-07-26: antes QUALQUER papel staff (estagiario/
        # financeiro incluídos) listava TODAS as solicitações. Agora staff
        # não-gestão vê só as de clientes da sua carteira — mesmo padrão de
        # visibilidade de centro_custos/compliance/bank_analysis, via subquery
        # única de client_ownership (sem N+1).
        q = q.where(SignatureRequest.client_id.in_(ids_clientes_visiveis(cu)))
    rows = (await db.execute(
        q.order_by(SignatureRequest.status, SignatureRequest.created_at.desc())
    )).scalars().all()

    # Anexar título do documento — títulos resolvidos em UMA query (evita N+1).
    doc_ids = {s.document_id for s in rows if s.document_id}
    titulos: dict[str, str] = {}
    if doc_ids:
        docs = (await db.execute(
            select(Document.id, Document.titulo).where(Document.id.in_(doc_ids))
        )).all()
        titulos = {did: titulo for did, titulo in docs}

    # Signatários (logins do portal de cada cliente) em UMA query — o frontend
    # (Assinaturas.tsx: isSignatario) exige `signatarios` em CADA item; sem o
    # campo a página quebrava com TypeError quando existia registro.
    client_ids = {s.client_id for s in rows if s.client_id}
    por_cliente: dict[str, list[User]] = {}
    if client_ids:
        portais = (await db.execute(select(User).where(
            User.client_id.in_(client_ids),
            User.role == UserRole.cliente_externo,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        ))).scalars().all()
        for u in portais:
            por_cliente.setdefault(u.client_id, []).append(u)

    # `hash_completo` (conferência de integridade) só para quem tem interesse
    # legítimo: o próprio cliente (a query já filtra por client_id acima) e
    # advogado+ (advogado, socio, admin, superadmin). Papéis de apoio
    # (estagiario/secretaria/financeiro) ficam com o `hash` abreviado.
    ve_hash_completo = (
        cu.role == UserRole.cliente_externo
        or ROLE_LEVEL.get(role_str(cu), 0) >= ROLE_LEVEL["advogado"]
    )
    out = []
    for s in rows:
        out.append({
            "id": s.id, "document_id": s.document_id,
            "documento": titulos.get(s.document_id, "—"),
            "client_id": s.client_id,
            "signatarios": [_signatario(u, s)
                            for u in por_cliente.get(s.client_id, [])],
            "status": s.status.value,
            # `hash` abreviado mantido por compatibilidade.
            "hash": s.hash_sha256[:16] + "…",
            "hash_completo": s.hash_sha256 if ve_hash_completo else None,
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

    # DOC-108: revalidação de integridade NO ACEITE. O hash foi calculado na
    # criação; se o arquivo físico tiver mudado desde então, o cliente estaria
    # aceitando conteúdo diferente do que foi solicitado. Reabre o arquivo,
    # recalcula o SHA-256 e compara; divergência → invalida (cancela) e rejeita.
    doc = (await db.execute(select(Document).where(
        Document.id == sr.document_id
    ))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=409, detail="Documento da solicitação não localizado")
    from app.core.config import get_settings as _gs
    full_path = f"{_gs().UPLOAD_DIR}/{doc.filepath}"
    try:
        with open(full_path, "rb") as f:
            hash_atual = hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        raise HTTPException(status_code=409, detail="Arquivo físico ausente — assinatura invalidada")

    ip = obter_ip_real(request)
    if not hmac.compare_digest(hash_atual, sr.hash_sha256):
        sr.status = SignatureStatus.cancelado   # invalida a solicitação
        await criar_audit_log(
            db, cu.id, cu.role.value, "ASSINATURA_REJEITADA",
            "signature_requests", sig_id,
            detalhes=(f"hash divergente esperado={sr.hash_sha256[:16]} "
                      f"atual={hash_atual[:16]}"),
            ip=ip,
        )
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail=("Documento foi alterado após a solicitação de assinatura "
                    "(hash divergente). Solicitação invalidada — gere uma nova."),
        )

    sr.status = SignatureStatus.assinado
    sr.assinado_em = datetime.now(timezone.utc)
    sr.assinado_por_user = cu.id
    # IP real do signatário (último salto do X-Forwarded-For), não o loopback do
    # proxy Nginx — este IP é evidência probatória da assinatura (MP 2.200-2).
    sr.ip = ip
    sr.user_agent = (request.headers.get("user-agent") or "")[:300]

    await criar_audit_log(
        db, cu.id, cu.role.value, "ASSINATURA", "signature_requests", sig_id,
        detalhes=f"hash_revalidado={hash_atual[:16]} ip={sr.ip}",
        ip=sr.ip,
    )
    await db.commit()
    return {"detail": "Documento assinado com sucesso",
            "comprovante": {
                "assinado_em": sr.assinado_em.isoformat(),
                # hash REVALIDADO no aceite (idêntico ao da solicitação — a
                # divergência já teria abortado acima).
                "hash_documento": hash_atual,
                "hash_revalidado": True,
                "ip": sr.ip,
            }}


@router.get("/{sig_id}/documento")
async def visualizar_documento(
    sig_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Preview autenticado do documento LIGADO à solicitação de assinatura
    (DOC-107). Dá ao cliente do portal como VER o que vai assinar, sem depender
    da infra de portal-download (outro agente). Cliente externo só acessa as
    suas próprias solicitações (isolamento por client_id); staff exige ownership
    do documento/caso. Cada acesso é registrado em audit log ('VIEW') — trilha
    de que a visualização foi disponibilizada antes do aceite."""
    sr = (await db.execute(select(SignatureRequest).where(
        SignatureRequest.id == sig_id,
        SignatureRequest.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    if cu.role == UserRole.cliente_externo:
        if sr.client_id != cu.client_id:
            raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    doc = (await db.execute(select(Document).where(
        Document.id == sr.document_id, Document.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    if cu.role != UserRole.cliente_externo:
        # staff: mesmo gate de ownership do GED usado na criação.
        from app.routers.documents import _verificar_acesso_documento
        await _verificar_acesso_documento(db, cu, doc)

    from app.core.config import get_settings as _gs
    full_path = f"{_gs().UPLOAD_DIR}/{doc.filepath}"
    import os as _os
    if not _os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="Arquivo físico ausente")

    await criar_audit_log(db, cu.id, cu.role.value, "VIEW",
                          "signature_requests", sr.id,
                          detalhes="preview do documento para assinatura")
    await db.commit()
    return FileResponse(
        full_path,
        media_type=doc.mimetype or "application/octet-stream",
        filename=(doc.titulo or "documento"),
    )
