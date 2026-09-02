# ── app/routers/documents.py ─────────────────────────────────────────────────
"""GED jurídico: intake, lifecycle, governança, integridade e ponte RAG.

O router mantém somente autorização/contrato HTTP e delega ingestão física,
versionamento, antimalware, análise assíncrona e purge a services/tasks.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func as sqlfunc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.publicacao_externa import confidencialidade_str, pode_publicar_externamente
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.client import Client
from app.models.document import DocConfidencialidade, Document
from app.models.document_rescan import DocumentHashRescanBatch, DocumentHashRescanItem
from app.models.redesign import DocumentTypeMaster
from app.models.user import User
from app.schemas.common import MsgResponse
from app.services import google_drive as gd
from app.services.document_content_policy import EXTENSOES_PERMITIDAS
from app.services.document_extraction_adapter import extrair_texto_compatibilidade
from app.services.document_format import ascii_seguro
from app.services.document_ingestion_orchestrator import ingerir_documento_local
from app.services.document_ingestion_service import (
    MalwareDetectadoError,
    preparar_ingestao_documento_local,
)
from app.services.document_malware_factory import (
    malware_scan_habilitado,
    obter_scanner_documentos,
)
from app.services.document_persistence_service import (
    DadosPersistenciaDocumento,
    PersistenciaDocumentoInvalidaError,
)
from app.services.document_rag_bridge import (
    DocumentRagBridgeError,
    desativar_rag_documento,
    indexar_documento_no_caso,
)
from app.services.document_reference_guard import exigir_documento_sem_referencias_bloqueantes
from app.services.document_upload_stream import UploadExcedeLimiteError, UploadVazioError
from app.services.document_version_service import (
    DocumentoAnteriorNaoEncontradoError,
    DocumentoAnteriorObsoletoError,
    DocumentoContextoDivergenteError,
    DocumentoGrupoInconsistenteError,
    DocumentoVersaoError,
    configurar_documento_raiz,
    preparar_nova_versao,
)
from app.services.malware_scan_service import MalwareScanIndisponivelError
from app.tasks.dispatcher import (
    agendar_analise_documento,
    agendar_indexacao,
)
from app.tasks.rescan_tasks import agendar_rescan

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documentos / GED"])

FORMATOS_SEM_INDEXACAO = {".doc", ".xls"}
TIPOS_LEGADOS = {"procuracao", "contrato", "decisao", "peticao", "prova", "outro"}


def _pode_acessar_confidencial(user: User, conf: str) -> bool:
    if conf in ("restrito", "confidencial", "segredo_justica"):
        return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]
    return True


def _exigir_papel(cu: User, minimo: str, detalhe: str) -> None:
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL[minimo]:
        raise HTTPException(status_code=403, detail=detalhe)


async def _verificar_acesso_cliente_sem_caso(db: AsyncSession, user: User, client_id: str) -> None:
    if is_gestao(user):
        return
    if user.role.value == "cliente_externo":
        if getattr(user, "client_id", None) == client_id:
            return
        raise HTTPException(status_code=403, detail="Sem permissão para este cliente")
    case_id = (
        await db.execute(
            select(Case.id)
            .where(
                Case.client_id == client_id,
                Case.deleted_at.is_(None),
                or_(
                    Case.advogado_responsavel_id == user.id,
                    Case.advogado_auxiliar_id == user.id,
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if case_id is None:
        raise HTTPException(status_code=403, detail="Sem permissão para este cliente")


async def _verificar_acesso_documento(db: AsyncSession, user: User, document: Document) -> None:
    if document.case_id:
        await verificar_acesso_caso(db, user, document.case_id)
        return
    if is_gestao(user) or document.uploaded_by == user.id:
        return
    if document.client_id:
        if user.role.value == "cliente_externo" and document.confidencialidade.value != "normal":
            raise HTTPException(status_code=403, detail="Documento interno ou restrito")
        await _verificar_acesso_cliente_sem_caso(db, user, document.client_id)
        return
    raise HTTPException(status_code=403, detail="Sem permissão para este documento")


async def _documento_ativo(db: AsyncSession, doc_id: str) -> Document:
    document = (
        await db.execute(
            select(Document).where(Document.id == doc_id, Document.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return document


async def _documento_para_governanca(db: AsyncSession, doc_id: str) -> Document:
    document = await db.scalar(select(Document).where(Document.id == doc_id))
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return document


async def _tipos_master_ativos(db: AsyncSession) -> list[DocumentTypeMaster]:
    rows = (
        await db.execute(
            select(DocumentTypeMaster)
            .where(DocumentTypeMaster.ativo.is_(True))
            .order_by(DocumentTypeMaster.ordem, DocumentTypeMaster.nome)
        )
    ).scalars().all()
    return list(rows)


def _nome_original_seguro(filename: str | None, fallback: str) -> str:
    nome = (filename or fallback).replace("\\", "/").rsplit("/", 1)[-1].strip()
    return (nome or fallback)[:255]


def _remote_path_documento(document: Document) -> str | None:
    filepath = str(document.filepath or "")
    if not filepath.startswith("drive://"):
        return None
    candidato = filepath[len("drive://") :].strip()
    if not candidato or candidato == str(document.drive_file_id or ""):
        return None
    return candidato


def _serializar_documento(document: Document) -> dict:
    return {
        "id": document.id,
        "titulo": document.titulo,
        "tipo": document.tipo,
        "filename": document.filename,
        "size_bytes": document.size_bytes,
        "confidencialidade": document.confidencialidade.value,
        "case_id": document.case_id,
        "client_id": document.client_id,
        "versao": document.versao,
        "integrity_status": document.integrity_status,
        "analysis_status": document.analysis_status,
        "rag_status": document.rag_status,
        "legal_hold": bool(document.legal_hold),
        "retention_until": document.retention_until,
        "created_at": document.created_at,
    }


def _serializar_detalhe(document: Document) -> dict:
    item = _serializar_documento(document)
    item.update({
        "descricao": document.descricao,
        "mimetype": document.mimetype,
        "sha256": document.sha256,
        "versao_grupo_id": document.versao_grupo_id,
        "versao_anterior_id": document.versao_anterior_id,
        "malware_scan_status": document.malware_scan_status,
        "malware_scanned_at": document.malware_scanned_at,
        "integrity_verified_at": document.integrity_verified_at,
        "analysis_updated_at": document.analysis_updated_at,
        "analysis_error_code": document.analysis_error_code,
        "analysis_source_sha256": document.analysis_source_sha256,
        "rag_knowledge_doc_id": document.rag_knowledge_doc_id,
        "rag_indexed_at": document.rag_indexed_at,
        "rag_source_sha256": document.rag_source_sha256,
        "publicado_portal": bool(document.publicado_portal),
        "publicado_em": document.publicado_em,
        "updated_at": document.updated_at,
    })
    return item


def _content_disposition(filename: str) -> str:
    nome = (filename or "documento").strip() or "documento"
    nome_ascii = ascii_seguro(nome)
    for char in ('"', ";", "\\", "/"):
        nome_ascii = nome_ascii.replace(char, "")
    nome_ascii = " ".join(nome_ascii.split()) or "documento"
    return f'attachment; filename="{nome_ascii}"; filename*=UTF-8\'\'{quote(nome, safe="")}'


def _full_path_local(document: Document) -> Path:
    raiz = Path(settings.UPLOAD_DIR).resolve()
    caminho = (raiz / str(document.filepath or "")).resolve()
    try:
        caminho.relative_to(raiz)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Referência de storage inválida") from exc
    return caminho


async def _validar_tipo(db: AsyncSession, tipo: str | None) -> str | None:
    if not tipo:
        return None
    tipos_validos = set(TIPOS_LEGADOS)
    try:
        tipos_validos |= {t.tipo_key for t in await _tipos_master_ativos(db)}
    except Exception as exc:
        logger.warning("Catálogo de tipos indisponível; exception_type=%s", type(exc).__name__)
    if tipo not in tipos_validos:
        raise HTTPException(status_code=422, detail="Tipo de documento inválido. Use GET /documents/tipos.")
    return tipo


async def _resolver_contexto_upload(
    db: AsyncSession,
    cu: User,
    *,
    case_id: str | None,
    client_id: str | None,
    documento_anterior_id: str | None,
) -> tuple[str | None, str | None, Document | None]:
    predecessor = None
    if documento_anterior_id:
        predecessor = await _documento_ativo(db, documento_anterior_id)
        await _verificar_acesso_documento(db, cu, predecessor)
        if not _pode_acessar_confidencial(cu, predecessor.confidencialidade.value):
            raise HTTPException(status_code=403, detail="Documento predecessor restrito — acesso negado")
        if case_id is None:
            case_id = predecessor.case_id
        if client_id is None:
            client_id = predecessor.client_id
        if case_id != predecessor.case_id or client_id != predecessor.client_id:
            raise HTTPException(status_code=422, detail="Nova versão deve manter o mesmo caso/cliente do predecessor")

    if case_id:
        case = await verificar_acesso_caso(db, cu, case_id)
        if client_id and case.client_id and client_id != case.client_id:
            raise HTTPException(status_code=422, detail="client_id não corresponde ao cliente do caso")
        client_id = case.client_id
    elif client_id:
        await _verificar_acesso_cliente_sem_caso(db, cu, client_id)
        cliente = await db.scalar(select(Client.id).where(Client.id == client_id, Client.deleted_at.is_(None)))
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return case_id, client_id, predecessor


@router.get("/policy")
async def politica_upload(cu: User = Depends(get_current_user)):
    del cu
    return {
        "extensions": sorted(EXTENSOES_PERMITIDAS),
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "confidentiality": [c.value for c in DocConfidencialidade],
        "malware_scan_enabled": malware_scan_habilitado(),
    }


@router.get("/tipos")
async def listar_tipos(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    del cu
    tipos = await _tipos_master_ativos(db)
    return {
        "data": [
            {
                "tipo_key": t.tipo_key,
                "nome": t.nome,
                "categoria": t.categoria,
                "descricao": t.descricao,
                "campos_extracao": t.campos_extracao,
                "extensoes_aceitas": t.extensoes_aceitas,
            }
            for t in tipos
        ],
        "total": len(tipos),
    }


class SugerirTipoRequest(BaseModel):
    doc_id: Optional[str] = None
    texto: Optional[str] = None
    nome_arquivo: Optional[str] = None
    analise: Optional[dict] = None


@router.post("/sugerir-tipo")
async def sugerir_tipo_documento(
    req: SugerirTipoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not req.doc_id and not (req.texto and req.texto.strip()):
        raise HTTPException(status_code=422, detail="Informe doc_id ou texto")
    texto = req.texto
    case_id = None
    if req.doc_id:
        document = await _documento_ativo(db, req.doc_id)
        await _verificar_acesso_documento(db, cu, document)
        if not _pode_acessar_confidencial(cu, document.confidencialidade.value):
            raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")
        case_id = document.case_id
        texto = texto or document.ocr_text
    if not texto or len(texto.strip()) < 40:
        raise HTTPException(status_code=422, detail="Sem texto suficiente para classificar")
    tipos = await _tipos_master_ativos(db)
    if not tipos:
        raise HTTPException(status_code=503, detail="Catálogo de tipos não populado")
    from app.services.documento_service import sugerir_tipo
    try:
        return await sugerir_tipo(
            db,
            cu.id,
            texto,
            tipos=[{"tipo_key": t.tipo_key, "nome": t.nome, "descricao": t.descricao} for t in tipos],
            case_id=case_id,
            doc_id=req.doc_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("sugerir-tipo indisponível; exception_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Serviço de IA indisponível no momento") from exc


@router.post("/upload", status_code=201)
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    titulo: str = Form(...),
    tipo: Optional[str] = Form(None),
    confidencialidade: str = Form("confidencial"),
    case_id: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    documento_anterior_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    titulo = (titulo or "").strip()
    if not titulo:
        raise HTTPException(status_code=422, detail="Título obrigatório")
    if len(titulo) > 255:
        raise HTTPException(status_code=422, detail="Título excede 255 caracteres")
    tipo = await _validar_tipo(db, tipo)
    try:
        conf_enum = DocConfidencialidade(confidencialidade)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Confidencialidade inválida") from exc
    if not _pode_acessar_confidencial(cu, conf_enum.value):
        raise HTTPException(status_code=403, detail="Somente sócio+ pode gravar documento em cofre restrito+")

    case_id, client_id, _ = await _resolver_contexto_upload(
        db,
        cu,
        case_id=case_id,
        client_id=client_id,
        documento_anterior_id=documento_anterior_id,
    )
    try:
        scanner = obter_scanner_documentos()
    except MalwareScanIndisponivelError as exc:
        raise HTTPException(status_code=503, detail="Validação antimalware indisponível") from exc

    try:
        resultado = await ingerir_documento_local(
            db,
            file,
            filename=file.filename,
            upload_root=Path(settings.UPLOAD_DIR),
            max_bytes=settings.MAX_UPLOAD_MB * 1024 * 1024,
            dados=DadosPersistenciaDocumento(
                titulo=titulo,
                tipo=tipo,
                confidencialidade=conf_enum,
                case_id=case_id,
                client_id=client_id,
                uploaded_by=cu.id,
                user_role=cu.role.value,
                documento_anterior_id=documento_anterior_id,
            ),
            scanner=scanner,
        )
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

    document = resultado.documento
    if case_id:
        from app.services.status_transicao import avancar_status_pos_commit
        await avancar_status_pos_commit(db, case_id, "documento_vinculado", user_id=cu.id)
    mecanismo_analise = None
    if case_id and document.ocr_text:
        mecanismo_analise = await agendar_analise_documento(
            document.id,
            cu.id,
            document.sha256,
            background_tasks,
        )

    resposta: dict = {
        "id": document.id,
        "detail": "Documento enviado",
        "versao": document.versao,
        "sha256": document.sha256,
        "integrity_status": document.integrity_status,
        "malware_scan_status": document.malware_scan_status,
        "analysis_status": document.analysis_status,
        "analysis_dispatch": mecanismo_analise,
    }
    if resultado.extracao.nfe:
        resposta["nfe"] = resultado.extracao.nfe
    if Path(document.filename).suffix.lower() in FORMATOS_SEM_INDEXACAO and not document.ocr_text:
        resposta["aviso"] = "Conteúdo não indexável no formato legado; converta para formato atual."
    return resposta


@router.get("/")
async def listar(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    case_id: Optional[str] = None,
    client_id: Optional[str] = None,
    search: Optional[str] = Query(None, max_length=200),
    tipo: Optional[str] = None,
    confidencialidade: Optional[str] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    classificacao_pendente: Optional[bool] = None,
    cursor_created_at: Optional[datetime] = Query(None),
    cursor_id: Optional[str] = Query(None, max_length=36),
    include_total: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if bool(cursor_created_at) != bool(cursor_id):
        raise HTTPException(status_code=422, detail="cursor_created_at e cursor_id devem ser informados juntos")
    conf_filtro = None
    if confidencialidade:
        try:
            conf_filtro = DocConfidencialidade(confidencialidade)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Confidencialidade inválida") from exc

    query = select(Document).where(Document.deleted_at.is_(None))
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        query = query.where(Document.confidencialidade.in_(["normal", "interno"]))
    if cu.role.value == "cliente_externo":
        if not getattr(cu, "client_id", None):
            query = query.where(Document.id.is_(None))
        else:
            query = query.where(Document.client_id == cu.client_id, Document.confidencialidade == "normal")
    elif not is_gestao(cu):
        casos_visiveis = select(Case.id).where(
            Case.deleted_at.is_(None),
            or_(Case.advogado_responsavel_id == cu.id, Case.advogado_auxiliar_id == cu.id),
        )
        clientes_visiveis = select(Case.client_id).where(
            Case.deleted_at.is_(None),
            Case.client_id.is_not(None),
            or_(Case.advogado_responsavel_id == cu.id, Case.advogado_auxiliar_id == cu.id),
        )
        query = query.where(or_(
            Document.case_id.in_(casos_visiveis),
            Document.case_id.is_(None) & Document.client_id.in_(clientes_visiveis),
            Document.case_id.is_(None) & Document.client_id.is_(None) & (Document.uploaded_by == cu.id),
        ))
    if case_id:
        query = query.where(Document.case_id == case_id)
    if client_id:
        query = query.where(Document.client_id == client_id)
    if tipo:
        query = query.where(Document.tipo == tipo)
    if conf_filtro is not None:
        query = query.where(Document.confidencialidade == conf_filtro)
    if classificacao_pendente is True:
        query = query.where(Document.tipo.is_(None))
    elif classificacao_pendente is False:
        query = query.where(Document.tipo.is_not(None))
    if data_inicio:
        query = query.where(Document.created_at >= datetime.combine(data_inicio, dtime.min, tzinfo=timezone.utc))
    if data_fim:
        query = query.where(
            Document.created_at < datetime.combine(data_fim + timedelta(days=1), dtime.min, tzinfo=timezone.utc)
        )
    if search and search.strip():
        termo = search.strip()
        escaped = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        vector = sqlfunc.to_tsvector(
            "portuguese",
            sqlfunc.coalesce(Document.titulo, "") + " " + sqlfunc.coalesce(Document.ocr_text, ""),
        )
        tsquery = sqlfunc.plainto_tsquery("portuguese", termo)
        query = query.where(or_(
            Document.titulo.ilike(f"%{escaped}%", escape="\\"),
            vector.op("@@")(tsquery),
        ))
    if cursor_created_at and cursor_id:
        query = query.where(or_(
            Document.created_at < cursor_created_at,
            (Document.created_at == cursor_created_at) & (Document.id < cursor_id),
        ))
    query = query.order_by(Document.created_at.desc(), Document.id.desc())

    total = None
    if include_total:
        total = (await db.execute(select(sqlfunc.count()).select_from(query.subquery()))).scalar()
    if cursor_created_at:
        rows = (await db.execute(query.limit(page_size))).scalars().all()
    else:
        rows = (await db.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    next_cursor = None
    if len(rows) == page_size:
        ultimo = rows[-1]
        next_cursor = {
            "created_at": ultimo.created_at.isoformat() if ultimo.created_at else None,
            "id": ultimo.id,
        }
    return {
        "data": [_serializar_documento(d) for d in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "next_cursor": next_cursor,
    }


class RescanRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    client_id: Optional[str] = None
    case_id: Optional[str] = None


@router.post("/integridade/rescan", status_code=202)
async def iniciar_rescan(
    payload: RescanRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role.value not in {"superadmin", "admin"}:
        raise HTTPException(status_code=403, detail="Rescan de integridade exige admin ou superadmin")
    ids = list(dict.fromkeys(payload.document_ids))
    batch = DocumentHashRescanBatch(
        id=str(uuid4()),
        cliente_id=payload.client_id,
        caso_id=payload.case_id,
        document_ids_json=json.dumps(ids) if ids else None,
        dry_run=False,
        status="pendente",
        criado_por=cu.id,
    )
    db.add(batch)
    await criar_audit_log(
        db, cu.id, cu.role.value, "RESCAN_INTEGRIDADE", "documents", batch.id,
        dados_depois={"document_count": len(ids), "client_scope": bool(payload.client_id), "case_scope": bool(payload.case_id)},
    )
    await db.commit()
    try:
        mecanismo = agendar_rescan(batch.id, background_tasks=background_tasks)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Fila de rescan indisponível") from exc
    batch.mecanismo = mecanismo
    await db.commit()
    return {"batch_id": batch.id, "status": batch.status, "mecanismo": mecanismo}


@router.get("/integridade/rescan/{batch_id}")
async def status_rescan(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role.value not in {"superadmin", "admin", "socio"}:
        raise HTTPException(status_code=403, detail="Consulta de integridade exige sócio+")
    batch = await db.get(DocumentHashRescanBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    itens = (
        await db.execute(
            select(DocumentHashRescanItem)
            .where(DocumentHashRescanItem.batch_id == batch_id, DocumentHashRescanItem.motivo.is_not(None))
            .limit(100)
        )
    ).scalars().all()
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "mecanismo": batch.mecanismo,
        "total_selecionado": batch.total_selecionado,
        "total_concluidos": batch.total_concluidos,
        "total_erros": batch.total_erros,
        "total_nao_disponiveis": batch.total_nao_disponiveis,
        "iniciado_em": batch.iniciado_em,
        "concluido_em": batch.concluido_em,
        "divergencias": [
            {"document_id": i.document_id, "status": i.status, "motivo": i.motivo}
            for i in itens
        ],
    }


@router.get("/{doc_id}")
async def detalhar(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    document = await _documento_ativo(db, doc_id)
    await _verificar_acesso_documento(db, cu, document)
    if not _pode_acessar_confidencial(cu, document.confidencialidade.value):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")
    if document.confidencialidade.value in {"restrito", "confidencial", "segredo_justica"}:
        await criar_audit_log(
            db, cu.id, cu.role.value, "VIEW_DOCUMENTO", "documents", doc_id,
            dados_depois={"storage": "drive" if document.drive_file_id else "local"},
        )
        await db.commit()
    return _serializar_detalhe(document)


@router.get("/{doc_id}/download")
async def download(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    document = await _documento_ativo(db, doc_id)
    await _verificar_acesso_documento(db, cu, document)
    if not _pode_acessar_confidencial(cu, document.confidencialidade.value):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")

    if document.drive_file_id:
        try:
            content = await asyncio.to_thread(
                gd.download_file,
                document.drive_file_id,
                remote_path=_remote_path_documento(document),
            )
        except gd.DriveIndisponivelError as exc:
            raise HTTPException(status_code=503, detail="Google Drive não configurado/indisponível") from exc
        except gd.DriveObjetoNaoEncontradoError as exc:
            raise HTTPException(status_code=410, detail="Arquivo remoto não encontrado") from exc
        except Exception as exc:
            logger.warning("Download Drive falhou; doc_id=%s exception_type=%s", doc_id, type(exc).__name__)
            raise HTTPException(status_code=502, detail="Falha no storage remoto") from exc
        await criar_audit_log(db, cu.id, cu.role.value, "DOWNLOAD", "documents", doc_id, dados_depois={"storage": "drive"})
        await db.commit()
        return Response(
            content=content,
            media_type=document.mimetype or "application/octet-stream",
            headers={"Content-Disposition": _content_disposition(document.filename)},
        )

    full_path = _full_path_local(document)
    if not full_path.exists():
        raise HTTPException(status_code=410, detail="Arquivo físico não encontrado")
    await criar_audit_log(db, cu.id, cu.role.value, "DOWNLOAD", "documents", doc_id, dados_depois={"storage": "local"})
    await db.commit()
    return FileResponse(str(full_path), filename=document.filename, media_type=document.mimetype or "application/octet-stream")


async def _soft_delete_documento(db: AsyncSession, cu: User, document: Document, *, storage: str) -> None:
    await desativar_rag_documento(db, document)
    document.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db, cu.id, cu.role.value, "DELETE", "documents", document.id,
        dados_depois={"storage": storage, "storage_preservado": True, "rag_desativado": True},
    )
    await db.commit()


@router.delete("/{doc_id}", response_model=MsgResponse)
async def remover(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    document = await _documento_ativo(db, doc_id)
    await _verificar_acesso_documento(db, cu, document)
    await exigir_documento_sem_referencias_bloqueantes(db, doc_id, acao="excluído")
    await _soft_delete_documento(db, cu, document, storage="drive" if document.drive_file_id else "local")
    return MsgResponse(detail="Documento removido")


class DocumentPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titulo: Optional[str] = None
    tipo: Optional[str] = None
    confidencialidade: Optional[str] = None


@router.patch("/{doc_id}")
async def atualizar_metadados(
    doc_id: str,
    req: DocumentPatchRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    document = await _documento_ativo(db, doc_id)
    await _verificar_acesso_documento(db, cu, document)
    if not _pode_acessar_confidencial(cu, document.confidencialidade.value):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")
    campos = req.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(status_code=422, detail="Nenhum campo para atualizar")
    alteracoes: list[str] = []
    if "titulo" in campos:
        novo = (campos["titulo"] or "").strip()
        if not novo or len(novo) > 255:
            raise HTTPException(status_code=422, detail="Título inválido")
        if novo != document.titulo:
            document.titulo = novo
            alteracoes.append("titulo")
    if "confidencialidade" in campos:
        try:
            conf = DocConfidencialidade(campos["confidencialidade"])
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="Confidencialidade inválida") from exc
        if not _pode_acessar_confidencial(cu, conf.value):
            raise HTTPException(status_code=403, detail="Somente sócio+ pode mover documento para o cofre")
        if conf != document.confidencialidade:
            document.confidencialidade = conf
            alteracoes.append("confidencialidade")
    if "tipo" in campos:
        novo_tipo = await _validar_tipo(db, campos["tipo"])
        if novo_tipo != document.tipo:
            document.tipo = novo_tipo
            alteracoes.append("tipo")
    if alteracoes:
        await criar_audit_log(
            db, cu.id, cu.role.value, "UPDATE", "documents", doc_id,
            dados_depois={"campos_alterados": sorted(set(alteracoes))},
        )
        await db.commit()
    return {
        "id": document.id,
        "titulo": document.titulo,
        "tipo": document.tipo,
        "confidencialidade": document.confidencialidade.value,
        "case_id": document.case_id,
        "client_id": document.client_id,
        "detail": "Metadados atualizados" if alteracoes else "Nada a alterar",
    }


class DocumentGovernanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retention_until: Optional[datetime] = None
    legal_hold: Optional[bool] = None
    legal_hold_reason: Optional[str] = Field(None, max_length=2000)
    motivo_alteracao: str = Field(..., min_length=5, max_length=500)


@router.get("/{doc_id}/governanca")
async def obter_governanca(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_papel(cu, "socio", "Governança documental exige sócio+")
    document = await _documento_para_governanca(db, doc_id)
    await _verificar_acesso_documento(db, cu, document)
    return {
        "document_id": document.id,
        "retention_until": document.retention_until,
        "legal_hold": bool(document.legal_hold),
        "legal_hold_reason": document.legal_hold_reason,
        "legal_hold_set_by": document.legal_hold_set_by,
        "legal_hold_set_at": document.legal_hold_set_at,
        "deleted_at": document.deleted_at,
    }


@router.patch("/{doc_id}/governanca")
async def atualizar_governanca(
    doc_id: str,
    req: DocumentGovernanceRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_papel(cu, "socio", "Governança documental exige sócio+")
    document = await _documento_para_governanca(db, doc_id)
    await _verificar_acesso_documento(db, cu, document)
    campos = req.model_dump(exclude_unset=True)
    alteracoes: list[str] = []
    if "retention_until" in campos:
        valor = req.retention_until
        if valor is not None and valor.tzinfo is None:
            raise HTTPException(status_code=422, detail="retention_until deve conter timezone")
        if valor != document.retention_until:
            document.retention_until = valor
            alteracoes.append("retention_until")
    if "legal_hold" in campos:
        if req.legal_hold:
            motivo_hold = (req.legal_hold_reason or "").strip()
            if len(motivo_hold) < 5:
                raise HTTPException(status_code=422, detail="Motivo do legal hold é obrigatório")
            document.legal_hold = True
            document.legal_hold_reason = motivo_hold
            document.legal_hold_set_by = cu.id
            document.legal_hold_set_at = datetime.now(timezone.utc)
        else:
            document.legal_hold = False
            document.legal_hold_reason = None
            document.legal_hold_set_by = None
            document.legal_hold_set_at = None
        alteracoes.append("legal_hold")
    if not alteracoes:
        raise HTTPException(status_code=422, detail="Nenhuma alteração de governança informada")
    await criar_audit_log(
        db, cu.id, cu.role.value, "DOCUMENT_GOVERNANCE", "documents", doc_id,
        detalhes="Alteração de retenção/legal hold",
        dados_depois={
            "campos_alterados": sorted(set(alteracoes)),
            "legal_hold": bool(document.legal_hold),
            "motivo_alteracao_informado": bool(req.motivo_alteracao.strip()),
        },
    )
    await db.commit()
    return await obter_governanca(doc_id, db, cu)


@router.post("/{doc_id}/reprocessar-analise", status_code=202)
async def reprocessar_analise(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_papel(cu, "advogado", "Reprocessamento de análise exige advogado+")
    document = await _documento_ativo(db, doc_id)
    await _verificar_acesso_documento(db, cu, document)
    if not _pode_acessar_confidencial(cu, document.confidencialidade.value):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")
    if not document.case_id or not document.ocr_text:
        raise HTTPException(status_code=422, detail="Documento sem caso/OCR para análise")
    document.analysis_status = "pending"
    document.analysis_error_code = None
    document.analysis_source_sha256 = document.sha256
    document.analysis_updated_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db, cu.id, cu.role.value, "REPROCESS_AI", "documents", doc_id,
        dados_depois={"analysis_status": "pending"},
    )
    await db.commit()
    mecanismo = await agendar_analise_documento(doc_id, cu.id, document.sha256, background_tasks)
    return {"document_id": doc_id, "analysis_status": "pending", "mecanismo": mecanismo}


@router.post("/{doc_id}/verificar-integridade", status_code=202)
async def verificar_integridade(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_papel(cu, "socio", "Verificação de integridade exige sócio+")
    document = await _documento_ativo(db, doc_id)
    await _verificar_acesso_documento(db, cu, document)
    batch = DocumentHashRescanBatch(
        id=str(uuid4()),
        cliente_id=document.client_id,
        caso_id=document.case_id,
        document_ids_json=json.dumps([doc_id]),
        dry_run=False,
        status="pendente",
        criado_por=cu.id,
    )
    db.add(batch)
    await db.commit()
    mecanismo = agendar_rescan(batch.id, background_tasks=background_tasks)
    batch.mecanismo = mecanismo
    await db.commit()
    return {"batch_id": batch.id, "document_id": doc_id, "mecanismo": mecanismo}


class DocumentRagRequest(BaseModel):
    ativo: bool = True


@router.post("/{doc_id}/rag")
async def configurar_rag_documento(
    doc_id: str,
    req: DocumentRagRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_papel(cu, "advogado", "Uso de documento na inteligência exige advogado+")
    document = await _documento_ativo(db, doc_id)
    await _verificar_acesso_documento(db, cu, document)
    if not _pode_acessar_confidencial(cu, document.confidencialidade.value):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")

    if not req.ativo:
        alterado = await desativar_rag_documento(db, document)
        await criar_audit_log(
            db, cu.id, cu.role.value, "RAG_DISABLE", "documents", doc_id,
            dados_depois={"rag_status": document.rag_status, "alterado": alterado},
        )
        await db.commit()
        return {"document_id": doc_id, "rag_status": document.rag_status}

    try:
        knowledge_doc, resultado = await indexar_documento_no_caso(db, document)
    except DocumentRagBridgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await criar_audit_log(
        db, cu.id, cu.role.value, "RAG_INDEX", "documents", doc_id,
        dados_depois={"rag_status": document.rag_status, "knowledge_doc_id": knowledge_doc.id},
    )
    await db.commit()
    mecanismo = None
    if knowledge_doc.status_indexacao != "indexado":
        mecanismo = await agendar_indexacao(knowledge_doc.id, background_tasks)
    return {
        "document_id": doc_id,
        "rag_status": document.rag_status,
        "knowledge_doc_id": knowledge_doc.id,
        "resultado": resultado,
        "mecanismo": mecanismo,
    }


class DocumentPublicacaoPortalRequest(BaseModel):
    publicado: bool


@router.patch("/{doc_id}/publicacao-portal")
async def publicar_no_portal(
    doc_id: str,
    req: DocumentPublicacaoPortalRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = await _documento_ativo(db, doc_id)
    await _verificar_acesso_documento(db, cu, d)
    if not _pode_acessar_confidencial(cu, d.confidencialidade.value):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")
    _exigir_papel(cu, "advogado", "Publicar ou despublicar no Portal exige advogado ou superior")
    if req.publicado:
        if confidencialidade_str(d) != DocConfidencialidade.normal.value:
            raise HTTPException(status_code=422, detail="Só documentos normais podem ser publicados no Portal")
        if not pode_publicar_externamente(cu, d):
            raise HTTPException(status_code=403, detail="A classificação atual impede publicação externa")
    ja_publicado = bool(d.publicado_portal)
    if ja_publicado != req.publicado:
        d.publicado_portal = req.publicado
        d.publicado_por = cu.id if req.publicado else None
        d.publicado_em = datetime.now(timezone.utc) if req.publicado else None
        await criar_audit_log(
            db, cu.id, cu.role.value,
            "PUBLISH_PORTAL" if req.publicado else "UNPUBLISH_PORTAL",
            "documents", doc_id,
            dados_depois={"publicado_portal": req.publicado},
        )
        await db.commit()
    return {
        "id": d.id,
        "publicado_portal": bool(d.publicado_portal),
        "publicado_por": d.publicado_por,
        "publicado_em": d.publicado_em.isoformat() if d.publicado_em else None,
    }


@router.post("/{doc_id}/classificar", dependencies=[Depends(rate_limit("doc-classificar", 15))])
async def classificar_tipo_documento(
    doc_id: str,
    aplicar: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    document = await _documento_ativo(db, doc_id)
    await _verificar_acesso_documento(db, cu, document)
    if not _pode_acessar_confidencial(cu, document.confidencialidade.value):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")
    from app.services.document_classifier import classificar_documento
    resultado = await classificar_documento(db, document.ocr_text or "")
    aplicado = False
    if aplicar and resultado.get("tipo_sugerido"):
        document.tipo = resultado["tipo_sugerido"]
        await criar_audit_log(
            db, cu.id, cu.role.value, "UPDATE", "documents", doc_id,
            dados_depois={"campos_alterados": ["tipo"], "origem": "classificacao_ia_hitl"},
        )
        await db.commit()
        aplicado = True
    return {
        "doc_id": doc_id,
        "aplicado": aplicado,
        "tipo_atual": document.tipo,
        **resultado,
        "aviso": "⚠️ SUGESTÃO gerada por IA — confirmação humana obrigatória.",
    }


@router.post("/drive/upload")
async def upload_para_drive(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    case_id: Optional[str] = Form(None),
    descricao: Optional[str] = Form(None),
    documento_anterior_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case_id, client_id, predecessor = await _resolver_contexto_upload(
        db,
        current_user,
        case_id=case_id,
        client_id=None,
        documento_anterior_id=documento_anterior_id,
    )
    folder_token = gd.case_folder_token(case_id) if case_id else None
    try:
        scanner = obter_scanner_documentos()
    except MalwareScanIndisponivelError as exc:
        raise HTTPException(status_code=503, detail="Validação antimalware indisponível") from exc

    try:
        ingestao = await preparar_ingestao_documento_local(
            file,
            filename=file.filename,
            upload_root=Path(settings.UPLOAD_DIR),
            max_bytes=settings.MAX_UPLOAD_MB * 1024 * 1024,
            scanner=scanner,
        )
    except UploadExcedeLimiteError as exc:
        raise HTTPException(status_code=413, detail=f"Arquivo excede {settings.MAX_UPLOAD_MB}MB") from exc
    except UploadVazioError as exc:
        raise HTTPException(status_code=422, detail="Arquivo vazio") from exc
    except MalwareDetectadoError as exc:
        raise HTTPException(status_code=422, detail="Arquivo bloqueado pela política antimalware") from exc
    except MalwareScanIndisponivelError as exc:
        raise HTTPException(status_code=503, detail="Validação antimalware indisponível") from exc

    file_id = ""
    remote_path = ""
    try:
        extracao = await extrair_texto_compatibilidade(db, ingestao, user_id=current_user.id)
        content = await asyncio.to_thread(ingestao.storage.caminho_staging_para_validacao.read_bytes)
        nome_remoto = f"{ingestao.doc_id}{ingestao.ext}"
        try:
            result = await asyncio.to_thread(
                gd.upload_file,
                content,
                nome_remoto,
                ingestao.mimetype,
                folder_token,
            )
        except gd.DriveIndisponivelError as exc:
            raise HTTPException(status_code=503, detail="Google Drive não configurado/indisponível") from exc
        except Exception as exc:
            logger.warning("Upload Drive falhou; exception_type=%s", type(exc).__name__)
            raise HTTPException(status_code=502, detail="Falha no storage remoto") from exc

        file_id = str(result.get("id") or "")
        remote_path = str(result.get("remote_path") or "")
        if not file_id or not remote_path:
            raise HTTPException(status_code=502, detail="Storage remoto não retornou identidade válida")

        agora = datetime.now(timezone.utc)
        tem_analise = bool(case_id and extracao.ocr_text)
        document = Document(
            id=ingestao.doc_id,
            case_id=case_id,
            client_id=client_id,
            titulo=ingestao.filename,
            descricao=descricao,
            filename=ingestao.filename,
            filepath=f"drive://{remote_path}",
            mimetype=ingestao.mimetype,
            size_bytes=ingestao.size_bytes,
            sha256=ingestao.sha256,
            ocr_text=extracao.ocr_text,
            drive_file_id=file_id,
            drive_link=result.get("webViewLink"),
            uploaded_by=current_user.id,
            confidencialidade=DocConfidencialidade.confidencial,
            malware_scan_status=ingestao.malware_scan_status.value,
            malware_scanned_at=agora if ingestao.malware_scan_status.value != "not_requested" else None,
            integrity_status="registered",
            analysis_status="pending" if tem_analise else "not_requested",
            analysis_updated_at=agora,
            analysis_source_sha256=ingestao.sha256 if tem_analise else None,
            rag_status="not_indexed" if tem_analise else None,
        )
        db.add(document)
        if predecessor:
            await preparar_nova_versao(db, document, documento_anterior_id=predecessor.id)
        else:
            configurar_documento_raiz(document)
        await criar_audit_log(
            db, current_user.id, current_user.role.value, "UPLOAD", "documents", document.id,
            dados_depois={
                "case_id": case_id,
                "client_id": client_id,
                "confidencialidade": document.confidencialidade.value,
                "size_bytes": ingestao.size_bytes,
                "storage": "drive",
                "malware_scan_status": document.malware_scan_status,
                "integrity_status": document.integrity_status,
            },
        )
        await db.commit()
    except Exception:
        await db.rollback()
        if remote_path or file_id:
            try:
                await asyncio.to_thread(gd.delete_file, file_id, remote_path=remote_path or None)
            except Exception:
                logger.error("Falha ao compensar objeto remoto após erro de persistência")
        raise
    finally:
        if not ingestao.storage.compensar():
            logger.error("Falha ao limpar staging do upload Drive")

    if case_id:
        from app.services.status_transicao import avancar_status_pos_commit
        await avancar_status_pos_commit(db, case_id, "documento_vinculado", user_id=current_user.id)
    mecanismo_analise = None
    if case_id and document.ocr_text:
        mecanismo_analise = await agendar_analise_documento(
            document.id, current_user.id, document.sha256, background_tasks
        )
    return {
        "id": document.id,
        "drive_file_id": file_id,
        "nome": document.filename,
        "link": document.drive_link,
        "download": result.get("webContentLink"),
        "sha256": document.sha256,
        "versao": document.versao,
        "malware_scan_status": document.malware_scan_status,
        "analysis_status": document.analysis_status,
        "analysis_dispatch": mecanismo_analise,
    }


async def _gate_drive_doc(db: AsyncSession, cu: User, file_id: str) -> Document:
    docs = (
        await db.execute(
            select(Document)
            .where(Document.drive_file_id == file_id, Document.deleted_at.is_(None))
            .limit(2)
        )
    ).scalars().all()
    if not docs:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if len(docs) != 1:
        raise HTTPException(status_code=409, detail="Referência remota ambígua — requer correção administrativa")
    document = docs[0]
    await _verificar_acesso_documento(db, cu, document)
    if not _pode_acessar_confidencial(cu, document.confidencialidade.value):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")
    return document


@router.get("/drive/{file_id}/link")
async def link_documento(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = await _gate_drive_doc(db, current_user, file_id)
    try:
        info = await asyncio.to_thread(gd.get_file_link, file_id)
    except gd.DriveIndisponivelError as exc:
        raise HTTPException(status_code=503, detail="Google Drive não configurado/indisponível") from exc
    await criar_audit_log(
        db, current_user.id, current_user.role.value, "VIEW_DOCUMENTO", "documents", document.id,
        dados_depois={"storage": "drive"},
    )
    await db.commit()
    return {"view": info.get("webViewLink"), "download": info.get("webContentLink"), "nome": document.filename}


@router.get("/drive/{file_id}/download")
async def download_documento(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = await _gate_drive_doc(db, current_user, file_id)
    try:
        content = await asyncio.to_thread(gd.download_file, file_id, remote_path=_remote_path_documento(document))
    except gd.DriveIndisponivelError as exc:
        raise HTTPException(status_code=503, detail="Google Drive não configurado/indisponível") from exc
    except gd.DriveObjetoNaoEncontradoError as exc:
        raise HTTPException(status_code=410, detail="Arquivo remoto não encontrado") from exc
    except Exception as exc:
        logger.warning("Download Drive falhou; exception_type=%s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Falha no storage remoto") from exc
    await criar_audit_log(
        db, current_user.id, current_user.role.value, "DOWNLOAD", "documents", document.id,
        dados_depois={"storage": "drive"},
    )
    await db.commit()
    return Response(
        content=content,
        media_type=document.mimetype or "application/octet-stream",
        headers={"Content-Disposition": _content_disposition(document.filename)},
    )


@router.delete("/drive/{file_id}")
async def deletar_documento_drive(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = await _gate_drive_doc(db, current_user, file_id)
    await exigir_documento_sem_referencias_bloqueantes(db, document.id, acao="excluído")
    await _soft_delete_documento(db, current_user, document, storage="drive")
    return {"ok": True}
