# ── app/routers/portal_documentos.py ─────────────────────────────────────────
# Portal do Cliente — solicitações de documentos (migration 084).
#
#   GET  /portal/solicitacoes-documentos → solicitações do PRÓPRIO cliente
#   POST /portal/solicitacoes-documentos/itens/{item_id}/upload → envia o
#        arquivo do item (multipart "file"), cria Document no GED do caso,
#        marca o item como enviado e recalcula o status da solicitação.
#
# Segurança (padrão portal.py):
#   • _exigir_cliente: role cliente_externo + client_id — o middleware já
#     confina o perfil a /api/portal/*, este é o gate por endpoint;
#   • isolamento por client_id em TODA query (nunca expõe dados de terceiros);
#   • upload reusa EXATAMENTE as validações de documents.py (extensões
#     permitidas, teto MAX_UPLOAD_MB, magic bytes server-side, arquivo salvo
#     como uploads/AAAA/MM/<uuid>.<ext> — o nome do cliente NUNCA vira path);
#   • audit log em toda escrita; rate limit por rota.
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
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.document import DocConfidencialidade, Document
from app.models.solicitacao_documento import (
    SolicitacaoDocumento,
    SolicitacaoDocumentoItem,
)
from app.models.user import User, UserRole
# Reuso EXATO das validações de upload do GED (não duplicar regra de negócio).
from app.services.document_content_policy import (
    EXTENSOES_PERMITIDAS,
    validar_conteudo,
)
from app.services.solicitacao_documento_service import recalcular_status

settings = get_settings()
logger = logging.getLogger("ejc.portal_documentos")
router = APIRouter(prefix="/portal", tags=["Portal do Cliente"])


def _exigir_cliente(cu: User) -> str:
    """Garante perfil cliente_externo com vínculo; retorna client_id (mesma
    checagem de portal.py)."""
    if cu.role != UserRole.cliente_externo or not cu.client_id:
        raise HTTPException(
            status_code=403, detail="Acesso exclusivo do Portal do Cliente"
        )
    return cu.client_id


@router.get("/solicitacoes-documentos",
            dependencies=[Depends(rate_limit("portal-solicitacoes-listar", 60))])
async def listar_solicitacoes_portal(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Solicitações de documentos do PRÓPRIO cliente (não deletadas), com os
    itens e o nome do arquivo já enviado (quando houver)."""
    client_id = _exigir_cliente(cu)

    sols = (await db.execute(
        select(SolicitacaoDocumento, Case.titulo, Case.numero_interno)
        .join(Case, Case.id == SolicitacaoDocumento.case_id)
        .where(
            SolicitacaoDocumento.client_id == client_id,   # ← isolamento
            SolicitacaoDocumento.deleted_at.is_(None),
        )
        .order_by(SolicitacaoDocumento.created_at.desc())
    )).all()

    # Itens de TODAS as solicitações numa única query (evita N+1 por visita
    # ao portal), agrupados em memória por solicitacao_id.
    itens_por_sol: dict[str, list] = {}
    if sols:
        todos_itens = (await db.execute(
            select(SolicitacaoDocumentoItem, Document.filename)
            .outerjoin(Document, Document.id == SolicitacaoDocumentoItem.documento_id)
            .where(SolicitacaoDocumentoItem.solicitacao_id.in_(
                [s.id for s, _, _ in sols]
            ))
            .order_by(SolicitacaoDocumentoItem.created_at)
        )).all()
        for i, filename in todos_itens:
            itens_por_sol.setdefault(i.solicitacao_id, []).append((i, filename))

    data = []
    for s, caso_titulo, numero_interno in sols:
        itens = itens_por_sol.get(s.id, [])
        data.append({
            "id": s.id,
            "case_id": s.case_id,
            "caso_titulo": caso_titulo,
            "numero_interno": numero_interno,
            "mensagem": s.mensagem,
            "created_at": s.created_at,
            "status": s.status,
            "itens": [
                {
                    "id": i.id,
                    "nome": i.nome,
                    "descricao": i.descricao,
                    "status": i.status,
                    "enviado_em": i.enviado_em,
                    "filename": filename,
                }
                for i, filename in itens
            ],
        })
    return {"data": data}


@router.post("/solicitacoes-documentos/itens/{item_id}/upload", status_code=201,
             dependencies=[Depends(rate_limit("portal-solicitacoes-upload", 20))])
async def upload_item_solicitacao(
    item_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Upload do documento pedido: valida vínculo (item → solicitação do
    PRÓPRIO cliente, ainda pendente), cria Document (confidencialidade normal)
    vinculado ao caso+cliente, marca o item como enviado, recalcula o status da
    solicitação e notifica o advogado responsável (sino)."""
    client_id = _exigir_cliente(cu)

    # ── Vínculo + isolamento: o item precisa pertencer a uma solicitação do
    # PRÓPRIO cliente (404 fora do escopo — não vaza existência) ─────────────
    row = (await db.execute(
        select(SolicitacaoDocumentoItem, SolicitacaoDocumento)
        .join(SolicitacaoDocumento,
              SolicitacaoDocumento.id == SolicitacaoDocumentoItem.solicitacao_id)
        .where(
            SolicitacaoDocumentoItem.id == item_id,
            SolicitacaoDocumento.client_id == client_id,   # ← isolamento
            SolicitacaoDocumento.deleted_at.is_(None),
        )
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    item, sol = row
    if item.status != "pendente":
        raise HTTPException(
            status_code=422, detail="Este documento já foi enviado"
        )

    # ── Validações de upload — MESMAS de documents.py ────────────────────────
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in EXTENSOES_PERMITIDAS:
        raise HTTPException(status_code=422, detail=f"Extensão não permitida: {ext}")

    conteudo = await file.read()
    if len(conteudo) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede {settings.MAX_UPLOAD_MB}MB",
        )
    # Magic bytes server-side — nunca confiar na extensão/content_type.
    mime_real = validar_conteudo(ext, conteudo)

    # ── Claim atômico do item ANTES de gravar o arquivo: uploads concorrentes
    # no mesmo item disputam o UPDATE condicional (row lock) e só um vence —
    # o perdedor recebe 422 e nada dele vai a disco (sem arquivo órfão).
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
        raise HTTPException(
            status_code=422, detail="Este documento já foi enviado"
        )

    # ── Persistência do arquivo (uploads/AAAA/MM/<uuid>.<ext> — o filename do
    # cliente NUNCA compõe o path: sem traversal por construção) ─────────────
    subdir = f"{agora.year}/{agora.month:02d}"
    os.makedirs(f"{settings.UPLOAD_DIR}/{subdir}", exist_ok=True)
    filepath = f"{subdir}/{doc_id}{ext}"
    async with aiofiles.open(f"{settings.UPLOAD_DIR}/{filepath}", "wb") as f:
        await f.write(conteudo)

    # Decisão: o upload do portal NÃO roda OCR/análise IA automática — o
    # documento entra como recebido e a indexação acontece quando o advogado
    # triá-lo no GED (evita custo de IA disparado por usuário externo).
    nome_arquivo = (file.filename or f"documento{ext}")[:255]
    d = Document(
        id=doc_id,
        titulo=item.nome[:255],
        tipo="outro",
        filename=nome_arquivo,
        filepath=filepath,
        mimetype=mime_real,
        size_bytes=len(conteudo),
        confidencialidade=DocConfidencialidade.normal,
        case_id=sol.case_id,
        client_id=sol.client_id,
        uploaded_by=cu.id,
    )
    db.add(d)

    # ── Recalcula o status agregado da solicitação (item já marcado no claim) ─
    demais = (await db.execute(
        select(SolicitacaoDocumentoItem.id, SolicitacaoDocumentoItem.status)
        .where(SolicitacaoDocumentoItem.solicitacao_id == sol.id)
    )).all()
    status_itens = [
        "enviado" if i_id == item.id else i_status
        for i_id, i_status in demais
    ]
    sol.status = recalcular_status(status_itens)

    # LGPD/princípio da necessidade: o audit log é persistente e
    # consultável; registrar o NOME do item (dado do cliente) é
    # desnecessário para a trilha — item.id + solicitacao identificam o
    # fato com rastreabilidade completa sem expor o conteúdo. O contrato do
    # módulo (test_document_content_policy) exige ausência de 'detalhes' no
    # audit do upload: a referência ao documento assinado basta.
    await criar_audit_log(
        db, cu.id, cu.role.value, "UPLOAD", "solicitacao_documento_itens",
        item.id,
        dados_depois={"documento_id": doc_id, "solicitacao_id": sol.id},
    )
    await db.commit()

    # ── Notifica o advogado responsável do caso (sino — fail-safe) ───────────
    try:
        from app.services.notification_service import notificar
        case = (await db.execute(select(Case).where(Case.id == sol.case_id)))\
            .scalar_one_or_none()
        if case and case.advogado_responsavel_id:
            ref = case.numero_interno or case.titulo or sol.case_id
            await notificar(
                db, case.advogado_responsavel_id,
                "Documento recebido do cliente",
                f"O cliente enviou o documento '{item.nome}' solicitado no "
                f"caso {ref} (solicitação {sol.status}).",
                tipo="documento", link=f"/casos/{sol.case_id}",
                forcar_sino=True,
            )
    except Exception as e:
        logger.warning(
            "[PortalDoc] notificação ao advogado falhou (item %s): %s",
            item.id, e,
        )

    return {
        "id": item.id,
        "status": sol.status,
        "item_status": item.status,
        "documento_id": doc_id,
        "filename": nome_arquivo,
    }
