# ── app/routers/legal_docs.py ────────────────────────────────────────────────
# Peças jurídicas com HITL ENFORÇADO:
# ai_generated=True NÃO avança para aprovada/final sem human_reviewed=True.
# Bloqueio em nível de código — não apenas UI.
from __future__ import annotations
import logging
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso, is_gestao
from app.models.user import User
from app.models.case import Case
from app.models.legal_doc import LegalDoc, PecaStatus
from app.models.audit_log import criar_audit_log
from app.services.case_intel import indexar_peca_rag
from app.services.document_format import aviso_rascunho_ia, padronizar_documento_juridico
from app.schemas.legal_doc import (
    LegalDocCreate, LegalDocUpdate, LegalDocRevisao,
    LegalDocResponse, LegalDocDetail,
)
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/legal-docs", tags=["Peças Jurídicas"])

STATUS_EXIGE_REVISAO = {"aprovada", "final", "protocolada"}

# Status "pronto para protocolar" → dispara checklist pré-protocolo (#CHK gatilho 2).
_STATUS_PRE_PROTOCOLO = {"aprovada", "final"}


async def _bg_checklist_protocolo(case_id: str, user_id: str):
    """Antes do protocolo: gera checklist por legislação (rascunho HITL). Fail-safe."""
    from app.core.database import AsyncSessionLocal
    from app.services.checklist_ia import gerar_checklist_ia
    try:
        async with AsyncSessionLocal() as bgdb:
            await gerar_checklist_ia(bgdb, case_id, "pre_protocolo", user_id)
    except Exception as e:
        logging.getLogger("ejc.legal_docs").warning(f"checklist pre_protocolo falhou: {e}")


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    case_id: Optional[str] = None,
    status_f: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(LegalDoc).where(LegalDoc.deleted_at.is_(None))
    # Ownership por caso (IDOR): não-gestão só vê peças dos seus casos
    # (responsável/auxiliar), de casos sem dono (legado) ou sem caso.
    if not is_gestao(cu):
        casos_visiveis = select(Case.id).where(
            Case.deleted_at.is_(None),
            (
                (Case.advogado_responsavel_id == cu.id)
                | (Case.advogado_auxiliar_id == cu.id)
                | (Case.advogado_responsavel_id.is_(None) & Case.advogado_auxiliar_id.is_(None))
            ),
        )
        q = q.where(LegalDoc.case_id.is_(None) | LegalDoc.case_id.in_(casos_visiveis))
    if case_id:
        q = q.where(LegalDoc.case_id == case_id)
    if status_f:
        q = q.where(LegalDoc.status == status_f)
    q = q.order_by(LegalDoc.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [LegalDocResponse.model_validate(d) for d in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/", response_model=LegalDocDetail, status_code=201)
async def criar(
    payload: LegalDocCreate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if getattr(payload, "case_id", None):
        await verificar_acesso_caso(db, cu, payload.case_id)
    dados = payload.model_dump()
    dados["titulo"] = padronizar_documento_juridico(dados.get("titulo", ""))[:255]
    dados["conteudo"] = padronizar_documento_juridico(dados.get("conteudo", ""))
    d = LegalDoc(
        id=str(uuid4()), created_by=cu.id,
        **dados,
    )
    db.add(d)
    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "legal_docs", d.id,
        detalhes=f"IA={payload.ai_generated}",
    )
    await db.commit()
    await db.refresh(d)
    # ETAPA 2 — produção interna alimenta a RAG (sanitizada, classificada).
    background.add_task(indexar_peca_rag, d.id)
    return d


@router.get("/{doc_id}", response_model=LegalDocDetail)
async def detalhe(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    # Ownership por caso (IDOR): leitura restrita a quem tem acesso ao caso.
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)
    return d


@router.patch("/{doc_id}", response_model=LegalDocDetail)
async def atualizar(
    doc_id: str, payload: LegalDocUpdate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    mudancas = payload.model_dump(exclude_unset=True)
    if "titulo" in mudancas and mudancas["titulo"] is not None:
        mudancas["titulo"] = padronizar_documento_juridico(mudancas["titulo"])[:255]
    if "conteudo" in mudancas and mudancas["conteudo"] is not None:
        mudancas["conteudo"] = padronizar_documento_juridico(mudancas["conteudo"])

    # ── BLOQUEIO HITL (em código, não só UI) ───────────────────────────
    novo_status = mudancas.get("status")
    if (novo_status in STATUS_EXIGE_REVISAO
            and d.ai_generated and not d.human_reviewed):
        raise HTTPException(
            status_code=422,
            detail="⛔ Peça gerada por IA exige revisão humana registrada "
                   "antes de aprovar (use POST /legal-docs/{id}/revisar). "
                   "Provimento OAB 205/2021.",
        )

    # Edição de conteúdo incrementa versão
    if "conteudo" in mudancas and mudancas["conteudo"] != d.conteudo:
        d.versao += 1

    status_antigo = d.status.value if hasattr(d.status, "value") else d.status
    for k, v in mudancas.items():
        setattr(d, k, v)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "legal_docs", doc_id)
    await db.commit()
    await db.refresh(d)
    # #CHK gatilho 2 — ao APROVAR/FINALIZAR a peça (pronta p/ protocolo), gera o
    # checklist pré-protocolo (rascunho HITL) em background. Só na transição.
    ns = mudancas.get("status")
    ns = ns.value if hasattr(ns, "value") else ns
    if ns in _STATUS_PRE_PROTOCOLO and status_antigo not in _STATUS_PRE_PROTOCOLO and d.case_id:
        background.add_task(_bg_checklist_protocolo, d.case_id, cu.id)
    return d


@router.post("/{doc_id}/revisar", response_model=LegalDocDetail)
async def revisar(
    doc_id: str, payload: LegalDocRevisao,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Registro de revisão humana — desbloqueia aprovação de peça IA."""
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    d.human_reviewed = payload.aprovado
    d.revisor_id = cu.id
    d.revisado_em = datetime.now(timezone.utc)
    d.notas_revisao = payload.notas
    d.status = PecaStatus.corrigida if payload.aprovado else PecaStatus.em_revisao

    await criar_audit_log(
        db, cu.id, cu.role.value, "REVISAO_HITL", "legal_docs", doc_id,
        detalhes=f"aprovado={payload.aprovado}",
    )
    await db.commit()
    await db.refresh(d)
    # ETAPA 2 — re-indexa a versão revisada (qualidade validada) na RAG.
    if payload.aprovado:
        background.add_task(indexar_peca_rag, doc_id)
    return d


@router.delete("/{doc_id}", response_model=MsgResponse)
async def remover(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)
    d.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "legal_docs", doc_id)
    await db.commit()
    return MsgResponse(detail="Peça removida")


# ═══ Exportação em PDF timbrado (logo institucional embutido) ═══
from fastapi.responses import Response
from app.services.pdf_service import peca_para_pdf_async


@router.get("/{doc_id}/pdf")
async def exportar_pdf(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(LegalDoc).where(LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    # Ownership por caso (IDOR): exportação restrita a quem tem acesso ao caso.
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    # Peca IA sem revisao: PDF sai com aviso de rascunho, sem simbolos instaveis.
    titulo = padronizar_documento_juridico(d.titulo)
    conteudo = padronizar_documento_juridico(d.conteudo)
    if d.ai_generated and not d.human_reviewed:
        conteudo = aviso_rascunho_ia() + "\n\n" + conteudo

    try:
        pdf_bytes = await peca_para_pdf_async(titulo, conteudo)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    await criar_audit_log(db, cu.id, cu.role.value, "DOWNLOAD", "legal_docs",
                          doc_id, detalhes="Exportação PDF")
    await db.commit()

    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in titulo)[:60]
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )

