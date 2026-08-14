# ── app/routers/documents.py ─────────────────────────────────────────────────
# GED: upload/download com controle de confidencialidade (cofre).
# Acesso a docs restritos: audit log obrigatório (LGPD art. 37).
import asyncio
import logging
import os
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Optional
from urllib.parse import quote
from uuid import uuid4

import aiofiles
import magic  # python-magic — validação por magic bytes (server-side)
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func as sqlfunc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.client import Client
from app.models.document import DocConfidencialidade, Document
from app.models.redesign import DocumentTypeMaster
from app.models.user import User
from app.schemas.common import MsgResponse
from app.services import google_drive as gd
from app.services.document_analysis_hook import analisar_documento_bg
from app.services.document_format import ascii_seguro
from app.services.document_reference_guard import exigir_documento_sem_referencias_bloqueantes
from app.services.ocr_service import extrair_texto, extrair_xml

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["Documentos / GED"])

EXTENSOES_PERMITIDAS = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".xlsx", ".xls", ".txt", ".md", ".xml"}
# Markdown entra como texto plano: aceito na ingestão universal e no GED
# (auditoria 12/08/2026: .md era rejeitado com "Formato não suportado").
# Legados sem extrator de texto (sem lib p/ binário OLE): upload aceito, mas o
# response avisa que o conteúdo não é indexável (ver bloco final do upload()).
FORMATOS_SEM_INDEXACAO = {".doc", ".xls"}

# Tipos legados do campo Document.tipo — continuam aceitos no upload mesmo que
# não existam no master (compatibilidade com o frontend atual). Os que existem
# no master (procuracao/contrato/peticao/outro) são validados por lá também.
TIPOS_LEGADOS = {"procuracao", "contrato", "decisao", "peticao", "prova", "outro"}

# Magic bytes esperados por extensão. O valor é o conjunto de MIME types
# aceitáveis que `magic.from_buffer` pode retornar para aquele formato.
# .txt fica de fora da exigência estrita (texto puro tem detecção ambígua).
MIME_POR_EXTENSAO: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    ".doc": {"application/msword", "application/x-ole-storage"},
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
    },
    ".xls": {"application/vnd.ms-excel", "application/x-ole-storage"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    # NF-e/XML: libmagic pode reportar application/xml, text/xml ou text/plain
    ".xml": {"application/xml", "text/xml", "text/plain"},
    # Markdown: libmagic pode reportar text/plain (texto puro) ou text/markdown
    ".md": {"text/plain", "text/markdown"},
}


def _validar_conteudo(ext: str, conteudo: bytes) -> str:
    """Valida magic bytes e retorna MIME derivado do conteúdo."""
    mime_real = magic.from_buffer(conteudo[:2048], mime=True)
    esperados = MIME_POR_EXTENSAO.get(ext)
    if esperados is None:
        return mime_real or "text/plain"
    if mime_real not in esperados:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Conteúdo do arquivo ({mime_real}) não corresponde à extensão {ext}."
            ),
        )
    return mime_real


def _pode_acessar_confidencial(user: User, conf: str) -> bool:
    """Cofre: restrito+ exige perfil socio ou superior."""
    if conf in ("restrito", "confidencial", "segredo_justica"):
        return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]
    return True


async def _verificar_acesso_cliente_sem_caso(
    db: AsyncSession,
    user: User,
    client_id: str,
) -> None:
    """Autoriza cliente avulso por gestão, titular externo ou caso atribuído."""
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


async def _verificar_acesso_documento(
    db: AsyncSession,
    user: User,
    document: Document,
) -> None:
    """Gate único para documento vinculado a caso, cliente ou apenas uploader."""
    if document.case_id:
        await verificar_acesso_caso(db, user, document.case_id)
        return
    if is_gestao(user) or document.uploaded_by == user.id:
        return
    if document.client_id:
        if (
            user.role.value == "cliente_externo"
            and document.confidencialidade.value != "normal"
        ):
            raise HTTPException(status_code=403, detail="Documento interno ou restrito")
        await _verificar_acesso_cliente_sem_caso(db, user, document.client_id)
        return
    raise HTTPException(status_code=403, detail="Sem permissão para este documento")


async def _tipos_master_ativos(db: AsyncSession) -> list[DocumentTypeMaster]:
    """Tipos ativos do master (document_types_master), ordenados para o seletor."""
    rows = (
        await db.execute(
            select(DocumentTypeMaster)
            .where(DocumentTypeMaster.ativo.is_(True))
            .order_by(DocumentTypeMaster.ordem, DocumentTypeMaster.nome)
        )
    ).scalars().all()
    return list(rows)


def _nome_original_seguro(filename: str | None, fallback: str) -> str:
    """Normaliza somente para metadado; o nome nunca participa do path físico."""
    nome = (filename or fallback).replace("\\", "/").rsplit("/", 1)[-1].strip()
    return (nome or fallback)[:255]


def _remote_path_documento(document: Document) -> str | None:
    """Extrai path remoto novo; marcador legado ``drive://<file_id>`` cai em fallback."""
    filepath = str(document.filepath or "")
    if not filepath.startswith("drive://"):
        return None
    candidato = filepath[len("drive://") :].strip()
    if not candidato or candidato == str(document.drive_file_id or ""):
        return None
    return candidato


def _content_disposition(filename: str) -> str:
    nome = (filename or "documento").strip() or "documento"
    nome_ascii = ascii_seguro(nome)
    for char in ('"', ";", "\\", "/"):
        nome_ascii = nome_ascii.replace(char, "")
    nome_ascii = " ".join(nome_ascii.split()) or "documento"
    return (
        f'attachment; filename="{nome_ascii}"; '
        f"filename*=UTF-8''{quote(nome, safe='')}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TIPOS DE DOCUMENTO (master) — R3
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/tipos")
async def listar_tipos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista os tipos de documento ativos do master para o seletor do frontend."""
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
    """Classifica em tipo_key do master como sugestão sujeita a HITL."""
    if not req.doc_id and not (req.texto and req.texto.strip()):
        raise HTTPException(status_code=422, detail="Informe doc_id ou texto")

    texto = req.texto
    case_id = None
    if req.doc_id:
        document = (
            await db.execute(
                select(Document).where(
                    Document.id == req.doc_id,
                    Document.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Documento não encontrado")
        await _verificar_acesso_documento(db, cu, document)
        if not _pode_acessar_confidencial(cu, document.confidencialidade.value):
            raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")
        case_id = document.case_id
        texto = texto or document.ocr_text

    if not texto or len(texto.strip()) < 40:
        raise HTTPException(
            status_code=422,
            detail="Sem texto suficiente para classificar (OCR vazio ou muito curto).",
        )

    tipos = await _tipos_master_ativos(db)
    if not tipos:
        raise HTTPException(
            status_code=503,
            detail="Catálogo de tipos (document_types_master) não populado — rode o seed.",
        )

    from app.services.documento_service import sugerir_tipo

    try:
        return await sugerir_tipo(
            db,
            cu.id,
            texto,
            tipos=[
                {
                    "tipo_key": t.tipo_key,
                    "nome": t.nome,
                    "descricao": t.descricao,
                }
                for t in tipos
            ],
            case_id=case_id,
            doc_id=req.doc_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("sugerir-tipo falhou (doc %s): %s", req.doc_id, exc, exc_info=True)
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
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if case_id:
        caso = await verificar_acesso_caso(db, cu, case_id)
        if client_id and client_id != caso.client_id:
            raise HTTPException(
                status_code=422,
                detail="client_id diverge do cliente do caso informado",
            )
        client_id = caso.client_id
    elif client_id:
        cli = (
            await db.execute(
                select(Client.id).where(
                    Client.id == client_id,
                    Client.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if cli is None:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        await _verificar_acesso_cliente_sem_caso(db, cu, client_id)

    try:
        conf_enum = DocConfidencialidade(confidencialidade)
    except ValueError as exc:
        validos = ", ".join(c.value for c in DocConfidencialidade)
        raise HTTPException(
            status_code=422,
            detail=f"Confidencialidade inválida: {confidencialidade}. Use: {validos}",
        ) from exc

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in EXTENSOES_PERMITIDAS:
        raise HTTPException(status_code=422, detail=f"Extensão não permitida: {ext}")

    if tipo:
        tipos_validos = set(TIPOS_LEGADOS)
        try:
            tipos_validos |= {t.tipo_key for t in await _tipos_master_ativos(db)}
        except Exception as exc:
            logger.warning("document_types_master indisponível na validação de tipo: %s", exc)
        if tipo not in tipos_validos:
            raise HTTPException(
                status_code=422,
                detail=f"Tipo de documento inválido: {tipo}. Use GET /documents/tipos.",
            )

    conteudo = await file.read()
    if len(conteudo) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede {settings.MAX_UPLOAD_MB}MB",
        )
    mime_real = _validar_conteudo(ext, conteudo)

    agora = datetime.now(timezone.utc)
    subdir = f"{agora.year}/{agora.month:02d}"
    os.makedirs(f"{settings.UPLOAD_DIR}/{subdir}", exist_ok=True)
    doc_id = str(uuid4())
    filepath = f"{subdir}/{doc_id}{ext}"
    full_path = f"{settings.UPLOAD_DIR}/{filepath}"

    async with aiofiles.open(full_path, "wb") as handle:
        await handle.write(conteudo)

    ocr_text = None
    nfe_info = None
    try:
        if ext == ".xml":
            res_xml = await asyncio.to_thread(extrair_xml, full_path)
            if res_xml:
                ocr_text = res_xml.get("texto")
                nfe_info = res_xml.get("nfe")
        else:
            ocr_text = await asyncio.to_thread(extrair_texto, full_path, mime_real)
    except Exception as exc:
        logger.warning("OCR falhou no upload doc %s: %s", doc_id, exc)

    document = Document(
        id=doc_id,
        titulo=titulo,
        tipo=tipo,
        filename=_nome_original_seguro(file.filename, f"documento{ext}"),
        filepath=filepath,
        mimetype=mime_real,
        size_bytes=len(conteudo),
        confidencialidade=conf_enum,
        ocr_text=ocr_text,
        case_id=case_id,
        client_id=client_id,
        uploaded_by=cu.id,
    )

    # Compatibilidade G3 mantida nesta onda. A identidade por título será
    # substituída por versionamento explícito em PR próprio, com testes de
    # concorrência e constraint após auditoria dos grupos existentes.
    if case_id:
        existente = (
            await db.execute(
                select(Document)
                .where(
                    Document.titulo == titulo,
                    Document.case_id == case_id,
                    Document.deleted_at.is_(None),
                )
                .order_by(Document.versao.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existente:
            grupo = existente.versao_grupo_id or existente.id
            document.versao = (existente.versao or 1) + 1
            document.versao_grupo_id = grupo
            document.versao_anterior_id = existente.id
        else:
            document.versao_grupo_id = doc_id

    db.add(document)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPLOAD",
        "documents",
        doc_id,
        dados_depois={
            "case_id": case_id,
            "client_id": client_id,
            "tipo": tipo,
            "confidencialidade": conf_enum.value,
            "size_bytes": len(conteudo),
            "storage": "local",
        },
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        try:
            os.unlink(full_path)
        except FileNotFoundError:
            pass
        except OSError:
            logger.error("Falha ao compensar arquivo órfão %s", filepath, exc_info=True)
        raise

    if case_id:
        from app.services.status_transicao import avancar_status_pos_commit

        await avancar_status_pos_commit(db, case_id, "documento_vinculado", user_id=cu.id)
    if case_id and ocr_text:
        background_tasks.add_task(analisar_documento_bg, case_id, ocr_text, doc_id, cu.id)

    resposta: dict = {"id": doc_id, "detail": "Documento enviado"}
    if nfe_info:
        resposta["nfe"] = nfe_info
    if ext in FORMATOS_SEM_INDEXACAO and not ocr_text:
        resposta["aviso"] = (
            "Conteúdo não indexável: formato legado sem extração de texto "
            f"({ext}). Converta para {'.docx' if ext == '.doc' else '.xlsx'} "
            "para habilitar busca por conteúdo e análise por IA."
        )
    return resposta


@router.get("/")
async def listar(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    case_id: Optional[str] = None,
    client_id: Optional[str] = None,
    search: Optional[str] = None,
    tipo: Optional[str] = Query(None, description="Filtra por tipo exato (tipo_key)"),
    confidencialidade: Optional[str] = Query(
        None,
        description="Filtra por nível exato (normal|interno|restrito|confidencial|segredo_justica)",
    ),
    data_inicio: Optional[date] = Query(None, description="created_at >= data (UTC)"),
    data_fim: Optional[date] = Query(None, description="created_at <= data (UTC, inclusivo)"),
    classificacao_pendente: Optional[bool] = Query(
        None,
        description="true → somente documentos sem tipo (tipo IS NULL)",
    ),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    conf_filtro: Optional[DocConfidencialidade] = None
    if confidencialidade:
        try:
            conf_filtro = DocConfidencialidade(confidencialidade)
        except ValueError as exc:
            validos = ", ".join(c.value for c in DocConfidencialidade)
            raise HTTPException(
                status_code=422,
                detail=f"Confidencialidade inválida: {confidencialidade}. Use: {validos}",
            ) from exc

    query = select(Document).where(Document.deleted_at.is_(None))
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        query = query.where(Document.confidencialidade.in_(["normal", "interno"]))
    if cu.role.value == "cliente_externo":
        if not getattr(cu, "client_id", None):
            query = query.where(Document.id.is_(None))
        else:
            query = query.where(
                Document.client_id == cu.client_id,
                Document.confidencialidade == "normal",
            )
    elif not is_gestao(cu):
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
        query = query.where(
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
        query = query.where(
            Document.created_at
            >= datetime.combine(data_inicio, dtime.min, tzinfo=timezone.utc)
        )
    if data_fim:
        query = query.where(
            Document.created_at
            < datetime.combine(
                data_fim + timedelta(days=1),
                dtime.min,
                tzinfo=timezone.utc,
            )
        )
    if search:
        query = query.where(
            (Document.titulo.ilike(f"%{search}%"))
            | (Document.ocr_text.ilike(f"%{search}%"))
        )
    query = query.order_by(Document.created_at.desc())

    total = (
        await db.execute(select(sqlfunc.count()).select_from(query.subquery()))
    ).scalar()
    rows = (
        await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return {
        "data": [
            {
                "id": document.id,
                "titulo": document.titulo,
                "tipo": document.tipo,
                "filename": document.filename,
                "size_bytes": document.size_bytes,
                "confidencialidade": document.confidencialidade.value,
                "case_id": document.case_id,
                "created_at": document.created_at,
            }
            for document in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{doc_id}/download")
async def download(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    document = (
        await db.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

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
            raise HTTPException(
                status_code=503,
                detail="Google Drive não configurado/indisponível",
            ) from exc
        except gd.DriveObjetoNaoEncontradoError as exc:
            raise HTTPException(status_code=410, detail="Arquivo remoto não encontrado") from exc
        except Exception as exc:
            logger.error("Falha ao baixar documento remoto %s", doc_id, exc_info=True)
            raise HTTPException(status_code=502, detail="Falha no storage remoto") from exc

        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "DOWNLOAD",
            "documents",
            doc_id,
            dados_depois={"storage": "drive"},
        )
        await db.commit()
        return Response(
            content=content,
            media_type=document.mimetype or "application/octet-stream",
            headers={"Content-Disposition": _content_disposition(document.filename)},
        )

    full_path = f"{settings.UPLOAD_DIR}/{document.filepath}"
    if not os.path.exists(full_path):
        raise HTTPException(status_code=410, detail="Arquivo físico não encontrado")

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "DOWNLOAD",
        "documents",
        doc_id,
        dados_depois={"storage": "local"},
    )
    await db.commit()
    return FileResponse(
        full_path,
        filename=document.filename,
        media_type=document.mimetype or "application/octet-stream",
    )


async def _soft_delete_documento(
    db: AsyncSession,
    cu: User,
    document: Document,
    *,
    storage: str,
) -> None:
    document.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "DELETE",
        "documents",
        document.id,
        dados_depois={"storage": storage},
    )
    await db.commit()


@router.delete("/{doc_id}", response_model=MsgResponse)
async def remover(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    document = (
        await db.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    await _verificar_acesso_documento(db, cu, document)
    await exigir_documento_sem_referencias_bloqueantes(
        db,
        doc_id,
        acao="excluído",
    )

    # Evita o defeito antigo: soft-delete local de metadata sem remover o objeto
    # remoto. A via canônica por doc_id também remove o objeto Drive antes de
    # ocultar a linha. Falha remota deixa o documento ativo para nova tentativa.
    if document.drive_file_id:
        try:
            await asyncio.to_thread(
                gd.delete_file,
                document.drive_file_id,
                remote_path=_remote_path_documento(document),
            )
        except gd.DriveIndisponivelError as exc:
            raise HTTPException(
                status_code=503,
                detail="Google Drive não configurado/indisponível",
            ) from exc
        except gd.DriveObjetoNaoEncontradoError:
            # Objeto já ausente: não há dado remoto órfão a preservar.
            logger.warning("Objeto remoto já ausente ao remover documento %s", doc_id)
        except Exception as exc:
            logger.error("Falha ao remover objeto remoto do documento %s", doc_id, exc_info=True)
            raise HTTPException(status_code=502, detail="Falha ao remover arquivo remoto") from exc
        await _soft_delete_documento(db, cu, document, storage="drive")
        return MsgResponse(detail="Documento removido")

    await _soft_delete_documento(db, cu, document, storage="local")
    return MsgResponse(detail="Documento removido")


class DocumentPatchRequest(BaseModel):
    """Somente metadados; vínculo com caso é operação de domínio dedicada."""

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
    """Atualiza título/tipo/confidencialidade; nunca movimenta evidência entre casos."""
    document = (
        await db.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    await _verificar_acesso_documento(db, cu, document)
    if not _pode_acessar_confidencial(cu, document.confidencialidade.value):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")

    campos = req.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(status_code=422, detail="Nenhum campo para atualizar")

    alteracoes: list[str] = []

    if "titulo" in campos:
        novo_titulo = (campos["titulo"] or "").strip()
        if not novo_titulo:
            raise HTTPException(status_code=422, detail="Título não pode ser vazio")
        if novo_titulo != document.titulo:
            document.titulo = novo_titulo
            alteracoes.append("titulo")

    if "confidencialidade" in campos:
        try:
            conf_enum = DocConfidencialidade(campos["confidencialidade"])
        except (ValueError, TypeError) as exc:
            validos = ", ".join(c.value for c in DocConfidencialidade)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Confidencialidade inválida: {campos['confidencialidade']}. "
                    f"Use: {validos}"
                ),
            ) from exc
        if not _pode_acessar_confidencial(cu, conf_enum.value):
            raise HTTPException(
                status_code=403,
                detail="Somente sócio+ pode mover documento para o cofre (restrito+)",
            )
        if conf_enum != document.confidencialidade:
            document.confidencialidade = conf_enum
            alteracoes.append("confidencialidade")

    if "tipo" in campos:
        novo_tipo = campos["tipo"]
        if novo_tipo:
            tipos_validos = set(TIPOS_LEGADOS)
            try:
                tipos_validos |= {t.tipo_key for t in await _tipos_master_ativos(db)}
            except Exception as exc:
                logger.warning("document_types_master indisponível: %s", exc)
            if novo_tipo not in tipos_validos:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Tipo de documento inválido: {novo_tipo}. "
                        "Use GET /documents/tipos."
                    ),
                )
        if novo_tipo != document.tipo:
            document.tipo = novo_tipo
            alteracoes.append("tipo")

    if alteracoes:
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "UPDATE",
            "documents",
            doc_id,
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


@router.post(
    "/{doc_id}/classificar",
    dependencies=[Depends(rate_limit("doc-classificar", 15))],
)
async def classificar_tipo_documento(
    doc_id: str,
    aplicar: bool = Query(
        False,
        description=(
            "Se true, grava o tipo sugerido em Document.tipo somente quando válido."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    document = (
        await db.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    await _verificar_acesso_documento(db, cu, document)
    if not _pode_acessar_confidencial(cu, document.confidencialidade.value):
        raise HTTPException(status_code=403, detail="Documento restrito — acesso negado")

    from app.services.document_classifier import classificar_documento

    resultado = await classificar_documento(db, document.ocr_text or "")
    aplicado = False
    if aplicar and resultado.get("tipo_sugerido"):
        document.tipo = resultado["tipo_sugerido"]
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "UPDATE",
            "documents",
            doc_id,
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


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE DRIVE — compatibilidade de endpoints; lifecycle usa o mesmo Document.
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/drive/upload")
async def upload_para_drive(
    file: UploadFile = File(...),
    case_id: Optional[str] = Form(None),
    descricao: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = None
    client_id = None
    folder_token = None
    if case_id:
        case = await verificar_acesso_caso(db, current_user, case_id)
        client_id = case.client_id
        folder_token = gd.case_folder_token(case_id)

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in EXTENSOES_PERMITIDAS:
        raise HTTPException(status_code=422, detail=f"Extensão não permitida: {ext}")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede {settings.MAX_UPLOAD_MB}MB",
        )
    mime = _validar_conteudo(ext, content)

    doc_id = str(uuid4())
    nome_original = _nome_original_seguro(file.filename, f"documento{ext}")
    nome_remoto = f"{doc_id}{ext}"
    try:
        result = await asyncio.to_thread(
            gd.upload_file,
            content,
            nome_remoto,
            mime,
            folder_token,
        )
    except gd.DriveIndisponivelError as exc:
        raise HTTPException(
            status_code=503,
            detail="Google Drive não configurado/indisponível",
        ) from exc
    except Exception as exc:
        logger.error("Falha no upload para o Drive", exc_info=True)
        raise HTTPException(status_code=502, detail="Falha no storage remoto") from exc

    file_id = str(result.get("id") or "")
    remote_path = str(result.get("remote_path") or "")
    if not file_id or not remote_path:
        try:
            if remote_path:
                await asyncio.to_thread(gd.delete_file, file_id, remote_path=remote_path)
        except Exception:
            logger.critical("Falha ao compensar upload Drive sem ID/path", exc_info=True)
        raise HTTPException(status_code=502, detail="Storage remoto não retornou identidade válida")

    document = Document(
        id=doc_id,
        case_id=case_id,
        client_id=client_id,
        titulo=nome_original,
        descricao=descricao,
        filename=nome_original,
        filepath=f"drive://{remote_path}",
        mimetype=mime,
        size_bytes=len(content),
        drive_file_id=file_id,
        drive_link=result.get("webViewLink"),
        uploaded_by=current_user.id,
        confidencialidade=DocConfidencialidade.confidencial,
        versao_grupo_id=doc_id,
    )
    db.add(document)
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "UPLOAD",
        "documents",
        doc_id,
        dados_depois={
            "case_id": case_id,
            "client_id": client_id,
            "confidencialidade": DocConfidencialidade.confidencial.value,
            "size_bytes": len(content),
            "storage": "drive",
        },
    )
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        try:
            await asyncio.to_thread(gd.delete_file, file_id, remote_path=remote_path)
        except Exception:
            logger.critical(
                "Falha ao compensar objeto remoto após erro de persistência doc %s",
                doc_id,
                exc_info=True,
            )
        raise HTTPException(status_code=500, detail="Falha ao registrar documento") from exc

    if case is not None:
        from app.services.status_transicao import avancar_status_pos_commit

        await avancar_status_pos_commit(
            db,
            case_id,
            "documento_vinculado",
            user_id=current_user.id,
        )

    return {
        "id": doc_id,
        "drive_file_id": file_id,
        "nome": nome_original,
        "link": result.get("webViewLink"),
        "download": result.get("webContentLink"),
    }


async def _gate_drive_doc(db: AsyncSession, cu: User, file_id: str) -> Document:
    docs = (
        await db.execute(
            select(Document)
            .where(
                Document.drive_file_id == file_id,
                Document.deleted_at.is_(None),
            )
            .limit(2)
        )
    ).scalars().all()
    if not docs:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if len(docs) != 1:
        # drive_file_id legado não tem unique constraint. Nunca escolher uma
        # linha arbitrária: isso poderia autorizar por um caso e operar o objeto
        # compartilhado por outro.
        raise HTTPException(
            status_code=409,
            detail="Referência remota ambígua — requer correção administrativa",
        )
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
    info = gd.get_file_link(file_id)
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "VIEW_DOCUMENTO",
        "documents",
        document.id,
        dados_depois={"storage": "drive"},
    )
    await db.commit()
    return {
        "view": info.get("webViewLink"),
        "download": info.get("webContentLink"),
        "nome": document.filename,
    }


@router.get("/drive/{file_id}/download")
async def download_documento(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = await _gate_drive_doc(db, current_user, file_id)
    try:
        content = await asyncio.to_thread(
            gd.download_file,
            file_id,
            remote_path=_remote_path_documento(document),
        )
    except gd.DriveIndisponivelError as exc:
        raise HTTPException(
            status_code=503,
            detail="Google Drive não configurado/indisponível",
        ) from exc
    except gd.DriveObjetoNaoEncontradoError as exc:
        raise HTTPException(status_code=410, detail="Arquivo remoto não encontrado") from exc
    except Exception as exc:
        logger.error("Falha ao baixar arquivo Drive", exc_info=True)
        raise HTTPException(status_code=502, detail="Falha no storage remoto") from exc

    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "DOWNLOAD",
        "documents",
        document.id,
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
    await exigir_documento_sem_referencias_bloqueantes(
        db,
        document.id,
        acao="excluído",
    )
    try:
        await asyncio.to_thread(
            gd.delete_file,
            file_id,
            remote_path=_remote_path_documento(document),
        )
    except gd.DriveIndisponivelError as exc:
        raise HTTPException(
            status_code=503,
            detail="Google Drive não configurado/indisponível",
        ) from exc
    except gd.DriveObjetoNaoEncontradoError:
        logger.warning("Objeto remoto já ausente ao remover documento %s", document.id)
    except Exception as exc:
        logger.error("Falha ao remover arquivo Drive", exc_info=True)
        raise HTTPException(status_code=502, detail="Falha ao remover arquivo remoto") from exc

    await _soft_delete_documento(db, current_user, document, storage="drive")
    return {"ok": True}
