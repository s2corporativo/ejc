# ── app/services/google_drive_service.py ─────────────────────────────────────
# Sincronização Google Drive → Base de Conhecimento RAG.
#
# Desenho de segurança:
# - Drive é fonte documental externa; o RAG interno continua sendo a base soberana.
# - Credenciais via Service Account em variável de ambiente/arquivo local, nunca no Git.
# - Deduplicação/versionamento usa upsert_documento(chave_origem='gdrive:<file_id>').
# - Metadados do Drive ficam em knowledge_docs.extra para rastreabilidade.
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion_service import upsert_documento
from app.services.ocr_service import extrair_texto

logger = logging.getLogger("ejc.google_drive")

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"

DEFAULT_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
    "image/jpeg",
    "image/png",
    GOOGLE_DOC_MIME,
    GOOGLE_SHEET_MIME,
}

EXT_BY_MIME = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

EXPORTS = {
    GOOGLE_DOC_MIME: ("text/plain", ".txt"),
    GOOGLE_SHEET_MIME: ("text/csv", ".csv"),
}

_sync_lock = asyncio.Lock()


@dataclass(slots=True)
class DriveFile:
    id: str
    name: str
    mime_type: str
    modified_time: str | None = None
    md5_checksum: str | None = None
    size: int | None = None
    web_view_link: str | None = None
    owners: list[dict[str, Any]] | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "DriveFile":
        size = data.get("size")
        try:
            size_int = int(size) if size is not None else None
        except (TypeError, ValueError):
            size_int = None
        return cls(
            id=data["id"],
            name=data.get("name") or data["id"],
            mime_type=data.get("mimeType") or "application/octet-stream",
            modified_time=data.get("modifiedTime"),
            md5_checksum=data.get("md5Checksum"),
            size=size_int,
            web_view_link=data.get("webViewLink"),
            owners=data.get("owners") or [],
        )


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "sim", "on"}


def drive_enabled() -> bool:
    return _env_bool("GOOGLE_DRIVE_ENABLED", False)


def knowledge_folder_id() -> str:
    return os.getenv("GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID", "").strip()


def shared_drive_id() -> str:
    return os.getenv("GOOGLE_DRIVE_SHARED_DRIVE_ID", "").strip()


def max_file_bytes() -> int:
    mb = int(os.getenv("GOOGLE_DRIVE_MAX_FILE_MB", "50") or "50")
    return mb * 1024 * 1024


def default_categoria() -> str:
    return os.getenv("GOOGLE_DRIVE_DEFAULT_CATEGORIA", "doutrina").strip() or "doutrina"


def allowed_mime_types() -> set[str]:
    raw = os.getenv("GOOGLE_DRIVE_ALLOWED_MIME_TYPES", "").strip()
    if not raw:
        return set(DEFAULT_ALLOWED_MIME_TYPES)
    return {item.strip() for item in raw.split(",") if item.strip()}


def _build_credentials():
    json_inline = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "").strip()
    file_path = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE", "").strip()

    if json_inline:
        try:
            info = json.loads(json_inline)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON inválido") from exc
        return service_account.Credentials.from_service_account_info(
            info, scopes=[DRIVE_SCOPE]
        )

    if file_path:
        if not os.path.exists(file_path):
            raise RuntimeError(
                f"GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE não encontrado: {file_path}"
            )
        return service_account.Credentials.from_service_account_file(
            file_path, scopes=[DRIVE_SCOPE]
        )

    raise RuntimeError(
        "Credencial Google Drive ausente. Defina GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE "
        "ou GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON no .env."
    )


def get_drive_client():
    creds = _build_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _supports_all_drives() -> bool:
    return bool(shared_drive_id())


def _file_fields() -> str:
    return (
        "nextPageToken, files("
        "id,name,mimeType,modifiedTime,md5Checksum,size,webViewLink,"
        "owners(displayName,emailAddress)"
        ")"
    )


def _list_files_sync(folder_id: str, limit: int | None = None) -> list[DriveFile]:
    service = get_drive_client()
    query = f"'{folder_id}' in parents and trashed = false"
    items: list[DriveFile] = []
    page_token: str | None = None
    supports = _supports_all_drives()

    while True:
        req = service.files().list(
            q=query,
            fields=_file_fields(),
            pageToken=page_token,
            pageSize=min(1000, limit or 1000),
            supportsAllDrives=supports,
            includeItemsFromAllDrives=supports,
            corpora="drive" if supports else "user",
            driveId=shared_drive_id() or None,
        )
        resp = req.execute()
        for raw in resp.get("files", []):
            items.append(DriveFile.from_api(raw))
            if limit and len(items) >= limit:
                return items
        page_token = resp.get("nextPageToken")
        if not page_token:
            return items


def _get_file_sync(file_id: str) -> DriveFile:
    service = get_drive_client()
    supports = _supports_all_drives()
    raw = service.files().get(
        fileId=file_id,
        fields="id,name,mimeType,modifiedTime,md5Checksum,size,webViewLink,owners(displayName,emailAddress)",
        supportsAllDrives=supports,
    ).execute()
    return DriveFile.from_api(raw)


def _download_drive_file_sync(file: DriveFile) -> tuple[bytes, str, str]:
    """Retorna (bytes, mime_final, extensao)."""
    service = get_drive_client()
    supports = _supports_all_drives()

    if file.mime_type in EXPORTS:
        export_mime, ext = EXPORTS[file.mime_type]
        request = service.files().export_media(fileId=file.id, mimeType=export_mime)
        mime_final = export_mime
    else:
        ext = EXT_BY_MIME.get(file.mime_type) or os.path.splitext(file.name)[1] or ".bin"
        request = service.files().get_media(fileId=file.id, supportsAllDrives=supports)
        mime_final = file.mime_type

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue(), mime_final, ext


def _texto_de_bytes(raw: bytes, mime_type: str, ext: str) -> str:
    if mime_type.startswith("text/") or ext.lower() in {".txt", ".csv"}:
        return raw.decode("utf-8", errors="ignore")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        texto = extrair_texto(tmp_path, mime_type)
        return texto or ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _extra(file: DriveFile, mime_final: str, ext: str) -> dict[str, Any]:
    return {
        "source": "google_drive",
        "drive": {
            "file_id": file.id,
            "name": file.name,
            "mime_type_original": file.mime_type,
            "mime_type_indexado": mime_final,
            "extensao": ext,
            "modified_time": file.modified_time,
            "md5_checksum": file.md5_checksum,
            "size": file.size,
            "web_view_link": file.web_view_link,
            "owners": file.owners or [],
        },
        "confidence_level": "media",
    }


async def ensure_sync_state_table(db: AsyncSession) -> None:
    await db.execute(sqltext("""
        CREATE TABLE IF NOT EXISTS google_drive_sync_state (
            folder_id TEXT PRIMARY KEY,
            last_start_page_token TEXT NULL,
            last_sync_at TIMESTAMPTZ NULL,
            last_status TEXT NULL,
            last_error TEXT NULL,
            total_files_seen INTEGER NOT NULL DEFAULT 0,
            total_files_ingested INTEGER NOT NULL DEFAULT 0,
            total_files_skipped INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))


async def update_sync_state(
    db: AsyncSession,
    *,
    folder_id: str,
    status: str,
    seen: int,
    ingested: int,
    skipped: int,
    error: str | None = None,
) -> None:
    await ensure_sync_state_table(db)
    await db.execute(sqltext("""
        INSERT INTO google_drive_sync_state (
            folder_id, last_sync_at, last_status, last_error,
            total_files_seen, total_files_ingested, total_files_skipped,
            created_at, updated_at
        ) VALUES (
            :folder_id, NOW(), :status, :error,
            :seen, :ingested, :skipped,
            NOW(), NOW()
        )
        ON CONFLICT (folder_id) DO UPDATE SET
            last_sync_at = EXCLUDED.last_sync_at,
            last_status = EXCLUDED.last_status,
            last_error = EXCLUDED.last_error,
            total_files_seen = EXCLUDED.total_files_seen,
            total_files_ingested = EXCLUDED.total_files_ingested,
            total_files_skipped = EXCLUDED.total_files_skipped,
            updated_at = NOW()
    """), {
        "folder_id": folder_id,
        "status": status,
        "error": (error or None),
        "seen": seen,
        "ingested": ingested,
        "skipped": skipped,
    })


async def get_sync_state(db: AsyncSession, folder_id: str) -> dict[str, Any] | None:
    await ensure_sync_state_table(db)
    row = (await db.execute(sqltext("""
        SELECT folder_id, last_start_page_token, last_sync_at, last_status,
               last_error, total_files_seen, total_files_ingested,
               total_files_skipped, created_at, updated_at
        FROM google_drive_sync_state
        WHERE folder_id = :folder_id
    """), {"folder_id": folder_id})).mappings().first()
    return dict(row) if row else None


async def listar_arquivos_pasta(folder_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    folder_id = (folder_id or knowledge_folder_id()).strip()
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID não configurado")
    files = await asyncio.to_thread(_list_files_sync, folder_id, limit)
    allowed = allowed_mime_types()
    return [
        {
            "id": f.id,
            "name": f.name,
            "mime_type": f.mime_type,
            "modified_time": f.modified_time,
            "size": f.size,
            "web_view_link": f.web_view_link,
            "indexavel": f.mime_type in allowed,
        }
        for f in files
    ]


async def _processar_arquivo(
    db: AsyncSession,
    file: DriveFile,
    *,
    categoria: str,
    confianca: str,
) -> dict[str, Any]:
    allowed = allowed_mime_types()
    if file.mime_type not in allowed:
        return {
            "file_id": file.id,
            "name": file.name,
            "status": "ignorado",
            "motivo": f"MIME não permitido: {file.mime_type}",
        }

    if file.size and file.size > max_file_bytes():
        return {
            "file_id": file.id,
            "name": file.name,
            "status": "ignorado",
            "motivo": f"Arquivo acima do limite: {file.size} bytes",
        }

    raw, mime_final, ext = await asyncio.to_thread(_download_drive_file_sync, file)
    if len(raw) > max_file_bytes():
        return {
            "file_id": file.id,
            "name": file.name,
            "status": "ignorado",
            "motivo": f"Arquivo baixado acima do limite: {len(raw)} bytes",
        }

    texto_extraido = await asyncio.to_thread(_texto_de_bytes, raw, mime_final, ext)
    if len((texto_extraido or "").strip()) < 50:
        return {
            "file_id": file.id,
            "name": file.name,
            "status": "erro",
            "motivo": "Texto extraído vazio ou insuficiente para indexação",
        }

    extra = _extra(file, mime_final, ext)
    extra["confidence_level"] = confianca

    resultado = await upsert_documento(
        db,
        titulo=file.name,
        categoria=categoria,
        conteudo=texto_extraido,
        chave_origem=f"gdrive:{file.id}",
        fonte=file.web_view_link or f"google_drive:{file.id}",
        extra=extra,
        confianca=confianca,
        embutir_vetores=True,
    )
    return {
        "file_id": file.id,
        "name": file.name,
        "status": resultado,
        "categoria": categoria,
        "chars": len(texto_extraido),
        "modified_time": file.modified_time,
        "link": file.web_view_link,
    }


async def sincronizar_pasta_conhecimento(
    db: AsyncSession,
    *,
    folder_id: str | None = None,
    limit: int | None = None,
    categoria: str | None = None,
    confianca: str = "media",
) -> dict[str, Any]:
    if not drive_enabled():
        raise RuntimeError("GOOGLE_DRIVE_ENABLED=false. Ative no .env para sincronizar.")

    folder_id = (folder_id or knowledge_folder_id()).strip()
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID não configurado")

    categoria = (categoria or default_categoria()).strip() or "doutrina"

    if _sync_lock.locked():
        return {
            "ok": False,
            "status": "em_execucao",
            "detail": "Já existe uma sincronização Google Drive → RAG em andamento.",
        }

    async with _sync_lock:
        seen = ingested = skipped = 0
        resultados: list[dict[str, Any]] = []
        status = "sucesso"
        erro_geral: str | None = None

        try:
            files = await asyncio.to_thread(_list_files_sync, folder_id, limit)
            seen = len(files)
            for file in files:
                try:
                    item = await _processar_arquivo(
                        db, file, categoria=categoria, confianca=confianca
                    )
                    resultados.append(item)
                    if item["status"] in {"novo", "atualizado", "inalterado"}:
                        ingested += 1
                    else:
                        skipped += 1
                    await db.commit()
                except HttpError as exc:
                    await db.rollback()
                    skipped += 1
                    msg = f"Google API: {str(exc)[:300]}"
                    logger.warning("[GoogleDrive:RAG] arquivo %s falhou: %s", file.id, msg)
                    resultados.append({
                        "file_id": file.id,
                        "name": file.name,
                        "status": "erro",
                        "motivo": msg,
                    })
                except Exception as exc:  # por arquivo: não aborta o lote
                    await db.rollback()
                    skipped += 1
                    msg = f"{type(exc).__name__}: {str(exc)[:300]}"
                    logger.warning("[GoogleDrive:RAG] arquivo %s falhou: %s", file.id, msg)
                    resultados.append({
                        "file_id": file.id,
                        "name": file.name,
                        "status": "erro",
                        "motivo": msg,
                    })

            if skipped and not ingested:
                status = "erro"
            elif skipped:
                status = "parcial"

        except Exception as exc:
            await db.rollback()
            status = "erro"
            erro_geral = f"{type(exc).__name__}: {str(exc)[:500]}"
            logger.error("[GoogleDrive:RAG] sincronização falhou: %s", erro_geral)
        finally:
            await update_sync_state(
                db,
                folder_id=folder_id,
                status=status,
                seen=seen,
                ingested=ingested,
                skipped=skipped,
                error=erro_geral,
            )
            await db.commit()

        return {
            "ok": status in {"sucesso", "parcial"},
            "status": status,
            "folder_id": folder_id,
            "categoria": categoria,
            "total_files_seen": seen,
            "total_files_ingested": ingested,
            "total_files_skipped": skipped,
            "resultados": resultados,
            "erro": erro_geral,
            "executado_em": datetime.now(timezone.utc).isoformat(),
        }


async def reindexar_arquivo(
    db: AsyncSession,
    file_id: str,
    *,
    categoria: str | None = None,
    confianca: str = "media",
) -> dict[str, Any]:
    if not drive_enabled():
        raise RuntimeError("GOOGLE_DRIVE_ENABLED=false. Ative no .env para sincronizar.")
    file = await asyncio.to_thread(_get_file_sync, file_id)
    resultado = await _processar_arquivo(
        db,
        file,
        categoria=(categoria or default_categoria()),
        confianca=confianca,
    )
    await db.commit()
    return resultado
