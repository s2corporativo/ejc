"""Workflow jurídico simplificado do GED.

Este router é aditivo e preserva o contrato legado de ``documents.py``. Ele
concentra as operações novas de UX em serviços explícitos, sem expor filepath,
Drive IDs, outbox ou conteúdo OCR em respostas/listagens.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func as sqlfunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import AuditLog, criar_audit_log
from app.models.document import DocConfidencialidade, Document
from app.models.redesign import DocumentTypeMaster
from app.models.user import User
from app.services.document_extraction_adapter import extrair_texto_compatibilidade
from app.services.document_ingestion_service import MalwareDetectadoError, preparar_ingestao_documento_local
from app.services.document_malware_factory import obter_scanner_documentos
from app.services.document_persistence_service import (
    ConteudoDocumentoPreparado,
    DadosPersistenciaDocumento,
    PersistenciaDocumentoInvalidaError,
    persistir_documento_local,
)
from app.services.document_upload_stream import UploadExcedeLimiteError, UploadVazioError
from app.services.document_ux_service import (
    aplicar_visibilidade_documentos,
    buscar_duplicado_exato_contexto,
    filtro_caixa_entrada,
    motivos_atencao,
    pode_acessar_confidencial,
    resolver_contexto_upload,
    status_operacional,
    verificar_acesso_documento,
)
from app.services.document_version_service import (
    DocumentoAnteriorNaoEncontradoError,
    DocumentoAnteriorObsoletoError,
    DocumentoContextoDivergenteError,
    DocumentoGrupoInconsistenteError,
    DocumentoVersaoError,
)
from app.services.malware_scan_service import MalwareScanIndisponivelError
from app.tasks.dispatcher import agendar_analise_documento

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["Documentos / GED"])
TIPOS_LEGADOS = {"procuracao", "contrato", "decisao", "peticao", "prova", "outro"}


def _conf_value(document: Document) -> str:
    return getattr(document.confidencialidade, "value", str(document.confidencialidade))


def _serializar_lista(document: Document) -> dict:
    return {
        "id": document.id,
        "titulo": document.titulo,
        "tipo": document.tipo,
        "filename": document.filename,
        "size_bytes": document.size_bytes,
        "confidencialidade": _conf_value(document),
        "case_id": document.case_id,
        "client_id": document.client_id,
        "versao": document.versao,
        "analysis_status": document.analysis_status,
        "integrity_status": document.integrity_status,
        "rag_status": document.rag_status,
        "legal_hold": bool(document.legal_hold),
        "retention_until": document.retention_until,
        "operational_status": status_operacional(document),
        "attention_reasons": motivos_atencao(document),
        "created_at": document.created_at,
    }


def _query_visivel(cu: User):
    query = select(Document).where(Document.deleted_at.is_(None))
    return aplicar_visibilidade_documentos(query, cu)


async def _contar(db: AsyncSession, query) -> int:
    total = await db.scalar(
        select(sqlfunc.count()).select_from(query.order_by(None).subquery())
    )
    return int(total or 0)


async def _documento_ativo(db: AsyncSession, doc_id: str) -> Document:
    document = await db.scalar(
        select(Document).where(Document.id == doc_id, Document.deleted_at.is_(None))
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return document


async def _validar_tipo(db: AsyncSession, tipo: str | None) -> str | None:
    if not tipo:
        return None
    tipos_validos = set(TIPOS_LEGADOS)
    rows = (
        await db.execute(
            select(DocumentTypeMaster.tipo_key).where(DocumentTypeMaster.ativo.is_(True))
        )
    ).scalars().all()
    tipos_validos.update(rows)
    if tipo not in tipos_validos:
        raise HTTPException(status_code=422, detail="Tipo de documento inválido")
    return tipo


@router.get("/workflow/stats")
async def estatisticas_documentais(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """KPIs exatos no servidor, sempre dentro do mesmo escopo de visibilidade."""

    base = _query_visivel(cu)
    agora = datetime.now(timezone.utc)
    inicio_mes = datetime(agora.year, agora.month, 1, tzinfo=timezone.utc)

    total = await _contar(db, base)
    confidenciais = await _contar(
        db,
        base.where(Document.confidencialidade != DocConfidencialidade.normal),
    )
    este_mes = await _contar(db, base.where(Document.created_at >= inicio_mes))
    inbox = await _contar(db, base.where(filtro_caixa_entrada()))

    tipo_query = select(Document.tipo, sqlfunc.count(Document.id)).where(
        Document.deleted_at.is_(None)
    )
    tipo_query = aplicar_visibilidade_documentos(tipo_query, cu)
    tipo_rows = (
        await db.execute(tipo_query.group_by(Document.tipo).order_by(sqlfunc.count(Document.id).desc()))
    ).all()
    por_tipo = [
        {"tipo": tipo or "outros", "total": int(qtd)}
        for tipo, qtd in tipo_rows
    ]
    return {
        "total": total,
        "confidenciais": confidenciais,
        "este_mes": este_mes,
        "inbox": inbox,
        "tipos_distintos": len(por_tipo),
        "por_tipo": por_tipo[:8],
    }


@router.get("/workflow/inbox")
async def caixa_entrada_documental(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    case_id: Optional[str] = None,
    client_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Itens visíveis que exigem classificação, vínculo ou correção operacional."""

    query = _query_visivel(cu).where(filtro_caixa_entrada())
    if case_id:
        query = query.where(Document.case_id == case_id)
    if client_id:
        query = query.where(Document.client_id == client_id)

    total = await _contar(db, query)
    rows = (
        await db.execute(
            query.order_by(Document.created_at.desc(), Document.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "data": [_serializar_lista(item) for item in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{doc_id}/versions")
async def listar_versoes_documento(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    document = await _documento_ativo(db, doc_id)
    await verificar_acesso_documento(db, cu, document)
    if not pode_acessar_confidencial(cu, _conf_value(document)):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")

    grupo = document.versao_grupo_id or document.id
    query = select(Document).where(
        Document.deleted_at.is_(None),
        Document.versao_grupo_id == grupo,
        Document.case_id == document.case_id,
        Document.client_id == document.client_id,
    )
    query = aplicar_visibilidade_documentos(query, cu)
    rows = (
        await db.execute(query.order_by(Document.versao.desc(), Document.created_at.desc()))
    ).scalars().all()
    return {
        "document_id": document.id,
        "group_id": grupo,
        "data": [
            {
                **_serializar_lista(item),
                "is_current": item.id == document.id,
                "versao_anterior_id": item.versao_anterior_id,
            }
            for item in rows
        ],
        "total": len(rows),
    }


@router.get("/{doc_id}/history")
async def historico_documento(
    doc_id: str,
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Histórico sanitizado: ação e horário, sem payload WORM, IP ou PII."""

    document = await _documento_ativo(db, doc_id)
    await verificar_acesso_documento(db, cu, document)
    if not pode_acessar_confidencial(cu, _conf_value(document)):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")
    rows = (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.entidade == "documents", AuditLog.registro_id == doc_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "document_id": doc_id,
        "data": [{"action": item.acao, "created_at": item.created_at} for item in rows],
        "total": len(rows),
    }


@router.post("/workflow/upload", status_code=201)
async def upload_workflow(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    titulo: str = Form(...),
    tipo: Optional[str] = Form(None),
    confidencialidade: str = Form("confidencial"),
    case_id: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    documento_anterior_id: Optional[str] = Form(None),
    permitir_duplicado: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Upload simples com versão explícita e dedupe exato por SHA-256."""

    titulo = (titulo or "").strip()
    if not titulo or len(titulo) > 255:
        raise HTTPException(status_code=422, detail="Título inválido")
    tipo = await _validar_tipo(db, tipo)
    try:
        conf = DocConfidencialidade(confidencialidade)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Confidencialidade inválida") from exc
    if not pode_acessar_confidencial(cu, conf.value):
        raise HTTPException(status_code=403, detail="Somente sócio+ pode gravar documento no cofre")

    predecessor = None
    if documento_anterior_id:
        predecessor = await _documento_ativo(db, documento_anterior_id)
    case_id, client_id = await resolver_contexto_upload(
        db,
        cu,
        case_id=case_id,
        client_id=client_id,
        predecessor=predecessor,
    )

    try:
        scanner = obter_scanner_documentos()
    except MalwareScanIndisponivelError as exc:
        raise HTTPException(status_code=503, detail="Validação antimalware indisponível") from exc

    duplicado: Document | None = None
    try:
        ingestao = await preparar_ingestao_documento_local(
            file,
            filename=file.filename,
            upload_root=Path(settings.UPLOAD_DIR),
            max_bytes=settings.MAX_UPLOAD_MB * 1024 * 1024,
            scanner=scanner,
        )
        async with ingestao:
            duplicado = await buscar_duplicado_exato_contexto(
                db,
                sha256=ingestao.sha256,
                case_id=case_id,
                client_id=client_id,
                uploaded_by=cu.id,
            )
            if duplicado is not None and not permitir_duplicado:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "exact_duplicate",
                        "message": "Arquivo idêntico já existe neste contexto.",
                        "document_id": duplicado.id,
                    },
                )

            extracao = await extrair_texto_compatibilidade(
                db,
                ingestao,
                user_id=cu.id,
            )
            if duplicado is not None and permitir_duplicado:
                # persistir_documento_local faz o commit; registrar antes mantém
                # o override e o novo Document na MESMA transação/rollback.
                await criar_audit_log(
                    db,
                    cu.id,
                    cu.role.value,
                    "DUPLICATE_OVERRIDE",
                    "documents",
                    ingestao.doc_id,
                    dados_depois={"duplicate_document_id": duplicado.id, "sha_match": True},
                )
            document = await persistir_documento_local(
                db,
                ingestao,
                dados=DadosPersistenciaDocumento(
                    titulo=titulo,
                    tipo=tipo,
                    confidencialidade=conf,
                    case_id=case_id,
                    client_id=client_id,
                    uploaded_by=cu.id,
                    user_role=cu.role.value,
                    documento_anterior_id=documento_anterior_id,
                ),
                conteudo=ConteudoDocumentoPreparado(ocr_text=extracao.ocr_text),
            )
    except HTTPException:
        raise
    except UploadExcedeLimiteError as exc:
        raise HTTPException(status_code=413, detail=f"Arquivo excede {settings.MAX_UPLOAD_MB}MB") from exc
    except UploadVazioError as exc:
        raise HTTPException(status_code=422, detail="Arquivo vazio") from exc
    except MalwareDetectadoError as exc:
        raise HTTPException(status_code=422, detail="Arquivo bloqueado pela política antimalware") from exc
    except MalwareScanIndisponivelError as exc:
        raise HTTPException(status_code=503, detail="Validação antimalware indisponível") from exc
    except DocumentoAnteriorNaoEncontradoError as exc:
        raise HTTPException(status_code=409, detail="Documento predecessor indisponível") from exc
    except DocumentoContextoDivergenteError as exc:
        raise HTTPException(status_code=422, detail="Contexto da nova versão diverge do predecessor") from exc
    except (DocumentoAnteriorObsoletoError, DocumentoGrupoInconsistenteError) as exc:
        raise HTTPException(status_code=409, detail="Grupo de versões requer saneamento antes de nova revisão") from exc
    except (DocumentoVersaoError, PersistenciaDocumentoInvalidaError) as exc:
        raise HTTPException(status_code=422, detail="Metadados de versionamento inválidos") from exc

    if case_id:
        from app.services.status_transicao import avancar_status_pos_commit

        await avancar_status_pos_commit(db, case_id, "documento_vinculado", user_id=cu.id)

    mecanismo = None
    if case_id and document.ocr_text:
        mecanismo = await agendar_analise_documento(
            document.id,
            cu.id,
            document.sha256,
            background_tasks,
        )

    return {
        **_serializar_lista(document),
        "detail": "Documento enviado",
        "sha256": document.sha256,
        "malware_scan_status": document.malware_scan_status,
        "analysis_dispatch": mecanismo,
        "duplicate_override": bool(duplicado is not None and permitir_duplicado),
    }
