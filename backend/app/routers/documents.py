# ── app/routers/documents.py ─────────────────────────────────────────────────
# GED: upload/download com controle de confidencialidade (cofre).
# Acesso a docs restritos: audit log obrigatório (LGPD art. 37).
import os
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

import aiofiles
import magic  # python-magic — validação por magic bytes (server-side)
from fastapi import BackgroundTasks, APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.document import Document
from app.models.case import Case
from app.models.audit_log import criar_audit_log
from app.core.ownership import verificar_acesso_caso, is_gestao
from app.schemas.common import MsgResponse
import asyncio
from app.services.ocr_service import extrair_texto

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["Documentos / GED"])

EXTENSOES_PERMITIDAS = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".xlsx", ".xls", ".txt"}

# Magic bytes esperados por extensão. O valor é o conjunto de MIME types
# aceitáveis que `magic.from_buffer` pode retornar para aquele formato.
# .txt fica de fora da exigência estrita (texto puro tem detecção ambígua).
MIME_POR_EXTENSAO: dict[str, set[str]] = {
    ".pdf":  {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "application/zip"},  # OOXML é um zip — magic às vezes reporta zip
    ".doc":  {"application/msword", "application/x-ole-storage"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              "application/zip"},
    ".xls":  {"application/vnd.ms-excel", "application/x-ole-storage"},
    ".jpg":  {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png":  {"image/png"},
}


def _validar_conteudo(ext: str, conteudo: bytes) -> str:
    """
    Valida magic bytes contra a extensão declarada. Retorna o MIME real
    (detectado do conteúdo) para persistir — nunca o content_type do cliente.
    Levanta HTTPException 415 se houver incompatibilidade.
    """
    mime_real = magic.from_buffer(conteudo[:2048], mime=True)
    esperados = MIME_POR_EXTENSAO.get(ext)
    if esperados is None:
        # .txt e similares: aceita, mas registra o MIME detectado
        return mime_real or "text/plain"
    if mime_real not in esperados:
        raise HTTPException(
            status_code=415,
            detail=f"Conteúdo do arquivo ({mime_real}) não corresponde à "
                   f"extensão {ext}.",
        )
    return mime_real


def _pode_acessar_confidencial(user: User, conf: str) -> bool:
    """Cofre: restrito+ exige perfil socio ou superior."""
    if conf in ("restrito", "confidencial", "segredo_justica"):
        return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]
    return True



async def _analisar_doc_bg(case_id: str, ocr_text: str, doc_id: str, user_id: str) -> None:
    """Dispara análise estratégica em background após upload de documento com OCR."""
    try:
        from app.services.analise_estrategica import analisar_caso
        from app.core.database import AsyncSessionLocal
        from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
        from sqlalchemy import text as _sql
        from uuid import uuid4 as _uuid4
        import json as _json

        async with AsyncSessionLocal() as db:
            row = await db.execute(
                _sql("SELECT titulo, area, numero_processo, client_id FROM cases WHERE id = :id"),
                {"id": case_id},
            )
            caso = row.fetchone()

            resultado = await analisar_caso(
                titulo=(caso.titulo if caso else "") or "",
                area=(caso.area if caso else "") or "",
                numero_processo=(caso.numero_processo if caso else "") or "",
                texto_documento=ocr_text[:4000],
                scope_client_id=(caso.client_id if caso else None),  # A2: RAG restrito ao cliente
                db=db,
            )

            fontes = None
            if isinstance(resultado, dict) and resultado.get("_fontes_rag"):
                fontes = _json.dumps(resultado["_fontes_rag"], ensure_ascii=False)[:2000]
            log = AILog(
                id=str(_uuid4()),
                user_id=user_id,
                case_id=case_id,
                tipo_uso=AITipoUso.analise_caso,
                modelo="auto-analise-doc",
                prompt_sanitizado=f"[auto] analise estrategica do documento {doc_id}",
                resposta=_json.dumps(resultado, ensure_ascii=False)[:8000],
                fontes_rag=fontes,
                status_hitl=AIStatusHITL.gerado,
            )
            db.add(log)
            await db.commit()
    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).warning("Hook analise doc falhou: %s", exc)

@router.post("/upload", status_code=201)
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    titulo: str = Form(...),
    tipo: Optional[str] = Form(None),
    confidencialidade: str = Form("normal"),
    case_id: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Validações
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in EXTENSOES_PERMITIDAS:
        raise HTTPException(status_code=422, detail=f"Extensão não permitida: {ext}")

    conteudo = await file.read()
    if len(conteudo) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede {settings.MAX_UPLOAD_MB}MB",
        )

    # Validação por magic bytes (server-side) — não confiar na extensão nem no
    # content_type do cliente. Retorna o MIME real, persistido abaixo.
    mime_real = _validar_conteudo(ext, conteudo)

    # Salvar no volume (estrutura: uploads/AAAA/MM/uuid.ext)
    agora = datetime.now(timezone.utc)
    subdir = f"{agora.year}/{agora.month:02d}"
    os.makedirs(f"{settings.UPLOAD_DIR}/{subdir}", exist_ok=True)
    doc_id = str(uuid4())
    filepath = f"{subdir}/{doc_id}{ext}"
    full_path = f"{settings.UPLOAD_DIR}/{filepath}"

    async with aiofiles.open(full_path, "wb") as f:
        await f.write(conteudo)

    # OCR em thread (não bloqueia o event loop); falha não impede upload
    import asyncio as _asyncio
    ocr_text = None
    try:
        ocr_text = await _asyncio.to_thread(extrair_texto, full_path, mime_real)
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "OCR falhou no upload doc %s: %s", doc_id, e
        )

    d = Document(
        id=doc_id, titulo=titulo, tipo=tipo,
        filename=file.filename, filepath=filepath,
        mimetype=mime_real, size_bytes=len(conteudo),
        confidencialidade=confidencialidade, ocr_text=ocr_text,
        case_id=case_id, client_id=client_id, uploaded_by=cu.id,
    )
    db.add(d)
    await criar_audit_log(
        db, cu.id, cu.role.value, "UPLOAD", "documents", doc_id,
        detalhes=f"{titulo} ({confidencialidade})",
    )
    await db.commit()
    # Hook: análise estratégica automática quando há OCR e case_id
    if case_id and ocr_text:
        background_tasks.add_task(_analisar_doc_bg, case_id, ocr_text, doc_id, cu.id)
    return {"id": doc_id, "detail": "Documento enviado"}


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=500),
    case_id: Optional[str] = None,
    client_id: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Document).where(Document.deleted_at.is_(None))
    # Esconder confidenciais de quem não pode ver
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        q = q.where(Document.confidencialidade.in_(["normal", "interno"]))
    # Ownership por caso (IDOR): não-gestão só vê docs dos seus casos
    # (responsável/auxiliar), de casos sem dono (legado/triagem) ou sem caso.
    # Espelha a semântica de core.ownership.verificar_acesso_caso.
    if not is_gestao(cu):
        casos_visiveis = select(Case.id).where(
            Case.deleted_at.is_(None),
            (
                (Case.advogado_responsavel_id == cu.id)
                | (Case.advogado_auxiliar_id == cu.id)
                | (Case.advogado_responsavel_id.is_(None) & Case.advogado_auxiliar_id.is_(None))
            ),
        )
        q = q.where(Document.case_id.is_(None) | Document.case_id.in_(casos_visiveis))
    if case_id:
        q = q.where(Document.case_id == case_id)
    if client_id:
        q = q.where(Document.client_id == client_id)
    if search:
        q = q.where(
            (Document.titulo.ilike(f"%{search}%"))
            | (Document.ocr_text.ilike(f"%{search}%"))   # busca por CONTEÚDO
        )
    q = q.order_by(Document.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [
            {"id": d.id, "titulo": d.titulo, "tipo": d.tipo,
             "filename": d.filename, "size_bytes": d.size_bytes,
             "confidencialidade": d.confidencialidade.value,
             "case_id": d.case_id, "created_at": d.created_at}
            for d in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/{doc_id}/download")
async def download(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(Document).where(
            Document.id == doc_id, Document.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Ownership (IDOR): documento de um caso só é acessível a quem tem o caso.
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    if not _pode_acessar_confidencial(cu, d.confidencialidade.value):
        raise HTTPException(
            status_code=403,
            detail="Documento restrito — acesso negado",
        )

    full_path = f"{settings.UPLOAD_DIR}/{d.filepath}"
    if not os.path.exists(full_path):
        raise HTTPException(status_code=410, detail="Arquivo físico não encontrado")

    # Audit de download (obrigatório — LGPD)
    await criar_audit_log(
        db, cu.id, cu.role.value, "DOWNLOAD", "documents", doc_id,
        detalhes=d.titulo,
    )
    await db.commit()

    return FileResponse(
        full_path, filename=d.filename,
        media_type=d.mimetype or "application/octet-stream",
    )


@router.delete("/{doc_id}", response_model=MsgResponse)
async def remover(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(Document).where(
            Document.id == doc_id, Document.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    # Ownership (IDOR): só quem tem o caso pode remover o documento dele.
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)
    d.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "documents", doc_id)
    await db.commit()
    return MsgResponse(detail="Documento removido")


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE DRIVE — upload, download e deleção de documentos
# ─────────────────────────────────────────────────────────────────────────────
from fastapi import UploadFile, File as FastFile, Form
from app.services import google_drive as gd
import os

@router.post("/drive/upload")
async def upload_para_drive(
    file: UploadFile = FastFile(...),
    case_id: str = Form(None),
    descricao: str = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload de documento direto para o Google Drive."""
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "Arquivo muito grande (máx 50 MB)")

    mime = file.content_type or "application/octet-stream"
    # Organizar em subpasta do caso se fornecido
    folder_id = None
    if case_id:
        folder_id = await _get_or_create_case_folder(case_id, db)

    result = gd.upload_file(content, file.filename or "documento", mime, folder_id)

    # Salvar referência no banco
    from sqlalchemy import text as sql_text
    import uuid
    doc_id = str(uuid.uuid4())
    await db.execute(sql_text("""
        INSERT INTO documents (id, case_id, nome, tipo, drive_file_id, drive_link, tamanho, created_by, created_at)
        VALUES (:id, :case_id, :nome, :tipo, :drive_file_id, :drive_link, :tamanho, :created_by, NOW())
        ON CONFLICT DO NOTHING
    """), {
        "id": doc_id,
        "case_id": case_id,
        "nome": file.filename or "documento",
        "tipo": mime,
        "drive_file_id": result["id"],
        "drive_link": result.get("webViewLink"),
        "tamanho": len(content),
        "created_by": current_user.id,
    })
    await db.commit()

    return {
        "id": doc_id,
        "drive_file_id": result["id"],
        "nome": file.filename,
        "link": result.get("webViewLink"),
        "download": result.get("webContentLink"),
    }


async def _gate_drive_doc(db: AsyncSession, cu: User, file_id: str):
    """Gate IDOR para docs do Google Drive (auditoria 2026-06-30).
    Resolve a linha em `documents` pelo drive_file_id e exige acesso ao caso
    (verificar_acesso_caso) ou, p/ doc sem caso, ser gestão ou o criador."""
    from sqlalchemy import text as sql_text
    row = (await db.execute(sql_text(
        "SELECT id, case_id, created_by FROM documents "
        "WHERE drive_file_id = :fid AND deleted_at IS NULL LIMIT 1"
    ), {"fid": file_id})).mappings().first()
    if not row:
        raise HTTPException(404, "Documento não encontrado")
    if row.get("case_id"):
        await verificar_acesso_caso(db, cu, row["case_id"])
    elif not (is_gestao(cu) or row.get("created_by") == cu.id):
        raise HTTPException(403, "Sem permissão para este documento")
    return row


@router.get("/drive/{file_id}/link")
async def link_documento(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna link de visualização e download de um documento no Drive."""
    await _gate_drive_doc(db, current_user, file_id)
    try:
        info = gd.get_file_link(file_id)
        return {
            "view": info.get("webViewLink"),
            "download": info.get("webContentLink"),
            "nome": info.get("name"),
        }
    except Exception as e:
        raise HTTPException(404, f"Arquivo não encontrado no Drive: {e}")


@router.get("/drive/{file_id}/download")
async def download_documento(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Proxy de download — baixa do Drive e retorna ao cliente."""
    await _gate_drive_doc(db, current_user, file_id)
    from fastapi.responses import Response
    try:
        content, mime = gd.download_file(file_id)
        info = gd.get_file_link(file_id)
        return Response(
            content=content,
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="{info.get("name","documento")}"'},
        )
    except Exception as e:
        raise HTTPException(404, f"Erro ao baixar arquivo: {e}")


@router.delete("/drive/{file_id}")
async def deletar_documento_drive(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove documento do Drive e do banco."""
    from sqlalchemy import text as sql_text
    try:
        gd.delete_file(file_id)
    except Exception:
        pass  # já foi removido do Drive
    await db.execute(
        sql_text("DELETE FROM documents WHERE drive_file_id = :fid AND created_by = :uid"),
        {"fid": file_id, "uid": current_user.id},
    )
    await db.commit()
    return {"ok": True}


async def _get_or_create_case_folder(case_id: str, db) -> str:
    """Cria subpasta no Drive para o caso se não existir. Retorna folder_id."""
    from sqlalchemy import text as sql_text
    row = (await db.execute(
        sql_text("SELECT drive_folder_id, titulo FROM cases WHERE id = :id"),
        {"id": case_id},
    )).mappings().first()
    if not row:
        return os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    if row.get("drive_folder_id"):
        return row["drive_folder_id"]
    # Criar subpasta
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    import json as _json
    sa_json = os.getenv("GOOGLE_DRIVE_SA_JSON")
    if not sa_json:
        return os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    creds = service_account.Credentials.from_service_account_info(
        _json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    parent = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    meta = {
        "name": f"{case_id[:8]} — {(row.get('titulo') or 'Caso')[:40]}",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent] if parent else [],
    }
    folder = svc.files().create(body=meta, fields="id").execute()
    folder_id = folder["id"]
    await db.execute(
        sql_text("UPDATE cases SET drive_folder_id = :fid WHERE id = :id"),
        {"fid": folder_id, "id": case_id},
    )
    await db.commit()
    return folder_id

