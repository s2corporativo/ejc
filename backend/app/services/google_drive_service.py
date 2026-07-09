# ── app/services/google_drive_service.py ─────────────────────────────────────
# Sincronização Google Drive → Base de Conhecimento RAG.
#
# Desenho de segurança:
# - Drive é fonte documental externa; o RAG interno continua sendo a base soberana.
# - Autenticação aceita OAuth do usuário ou Service Account, sempre fora do Git.
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

from google.auth.transport.requests import Request
from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.google_drive_taxonomy import DriveTaxonomyDecision, classificar_drive_file
from app.services.ingestion_service import upsert_documento
from app.services.ocr_service import extrair_texto

logger = logging.getLogger("ejc.google_drive")

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"

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
    path: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any], *, path: str = "") -> "DriveFile":
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
            path=path.strip("/"),
        )

    @property
    def full_path(self) -> str:
        return f"{self.path}/{self.name}".strip("/")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "sim", "on"}


def drive_enabled() -> bool:
    return _env_bool("GOOGLE_DRIVE_ENABLED", False)


def auto_categorizar_enabled() -> bool:
    return _env_bool("GOOGLE_DRIVE_AUTO_CATEGORIZAR", True)


def knowledge_folder_id() -> str:
    return os.getenv("GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID", "").strip()


def shared_drive_id() -> str:
    return os.getenv("GOOGLE_DRIVE_SHARED_DRIVE_ID", "").strip()


def max_file_bytes() -> int:
    mb = int(os.getenv("GOOGLE_DRIVE_MAX_FILE_MB", "50") or "50")
    return mb * 1024 * 1024


def default_categoria() -> str:
    # Valor legado era "doutrina". O padrão operacional agora é "auto" para
    # evitar que peças práticas, leis e jurisprudência entrem com etiqueta errada.
    return os.getenv("GOOGLE_DRIVE_DEFAULT_CATEGORIA", "auto").strip() or "auto"


def allowed_mime_types() -> set[str]:
    raw = os.getenv("GOOGLE_DRIVE_ALLOWED_MIME_TYPES", "").strip()
    if not raw:
        return set(DEFAULT_ALLOWED_MIME_TYPES)
    return {item.strip() for item in raw.split(",") if item.strip()}


def auth_status() -> dict[str, Any]:
    return {
        "auth_mode": os.getenv("GOOGLE_DRIVE_AUTH_MODE", "auto").strip().lower() or "auto",
        "oauth_user_file_configurado": bool(os.getenv("GOOGLE_DRIVE_OAUTH_USER_FILE", "").strip()),
        "oauth_user_json_configurado": bool(os.getenv("GOOGLE_DRIVE_OAUTH_USER_JSON", "").strip()),
        "oauth_refresh_token_configurado": bool(os.getenv("GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN", "").strip()),
        "service_account_file_configurado": bool(os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE", "").strip()),
        "service_account_json_configurado": bool(os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "").strip()),
    }


def _refresh_if_needed(creds):
    # Credenciais authorized_user normalmente vêm sem access_token inicial.
    # Se houver refresh_token, renovamos aqui para falhar cedo com erro claro.
    if not creds.valid and getattr(creds, "refresh_token", None):
        creds.refresh(Request())
    return creds


def _credentials_from_oauth_user_json(raw_json: str):
    try:
        info = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_DRIVE_OAUTH_USER_JSON inválido") from exc
    creds = user_credentials.Credentials.from_authorized_user_info(
        info, scopes=[DRIVE_SCOPE]
    )
    return _refresh_if_needed(creds)


def _credentials_from_oauth_user_file(path: str):
    if not os.path.exists(path):
        raise RuntimeError(f"GOOGLE_DRIVE_OAUTH_USER_FILE não encontrado: {path}")
    creds = user_credentials.Credentials.from_authorized_user_file(
        path, scopes=[DRIVE_SCOPE]
    )
    return _refresh_if_needed(creds)


def _credentials_from_oauth_refresh_token():
    client_id = os.getenv("GOOGLE_DRIVE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_DRIVE_OAUTH_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN", "").strip()
    if not (client_id and client_secret and refresh_token):
        return None
    creds = user_credentials.Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=[DRIVE_SCOPE],
    )
    return _refresh_if_needed(creds)


def _credentials_from_service_account_json(raw_json: str):
    try:
        info = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON inválido") from exc
    return service_account.Credentials.from_service_account_info(
        info, scopes=[DRIVE_SCOPE]
    )


def _credentials_from_service_account_file(path: str):
    if not os.path.exists(path):
        raise RuntimeError(f"GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE não encontrado: {path}")
    return service_account.Credentials.from_service_account_file(
        path, scopes=[DRIVE_SCOPE]
    )


def _build_credentials():
    """Constrói credenciais Google Drive.

    Ordem em GOOGLE_DRIVE_AUTH_MODE=auto:
    1) OAuth authorized_user em arquivo/JSON ou refresh token;
    2) Service Account em JSON/arquivo.

    Isto evita travar quando a organização bloqueia criação de chaves de
    Service Account por `iam.managed.disableServiceAccountKeyCreation`.
    """
    auth_mode = os.getenv("GOOGLE_DRIVE_AUTH_MODE", "auto").strip().lower() or "auto"
    if auth_mode not in {"auto", "oauth", "service_account"}:
        raise RuntimeError(
            "GOOGLE_DRIVE_AUTH_MODE inválido. Use auto, oauth ou service_account."
        )

    if auth_mode in {"auto", "oauth"}:
        oauth_user_json = os.getenv("GOOGLE_DRIVE_OAUTH_USER_JSON", "").strip()
        oauth_user_file = os.getenv("GOOGLE_DRIVE_OAUTH_USER_FILE", "").strip()
        if oauth_user_json:
            return _credentials_from_oauth_user_json(oauth_user_json)
        if oauth_user_file:
            return _credentials_from_oauth_user_file(oauth_user_file)
        refresh_creds = _credentials_from_oauth_refresh_token()
        if refresh_creds is not None:
            return refresh_creds

    if auth_mode in {"auto", "service_account"}:
        sa_json = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "").strip()
        sa_file = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE", "").strip()
        if sa_json:
            return _credentials_from_service_account_json(sa_json)
        if sa_file:
            return _credentials_from_service_account_file(sa_file)

    raise RuntimeError(
        "Credencial Google Drive ausente. Configure uma das opções: "
        "GOOGLE_DRIVE_OAUTH_USER_FILE, GOOGLE_DRIVE_OAUTH_USER_JSON, "
        "GOOGLE_DRIVE_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN, "
        "GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE ou GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON."
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


def _list_children_sync(
    service,
    folder_id: str,
    *,
    limit: int | None,
    path: str,
    items: list[DriveFile],
    visited: set[str],
) -> None:
    if folder_id in visited:
        return
    visited.add(folder_id)

    query = f"'{folder_id}' in parents and trashed = false"
    page_token: str | None = None
    supports = _supports_all_drives()

    while True:
        if limit and len(items) >= limit:
            return
        req = service.files().list(
            q=query,
            fields=_file_fields(),
            pageToken=page_token,
            pageSize=1000,
            supportsAllDrives=supports,
            includeItemsFromAllDrives=supports,
            corpora="drive" if supports else "user",
            driveId=shared_drive_id() or None,
        )
        resp = req.execute()
        for raw in resp.get("files", []):
            f = DriveFile.from_api(raw, path=path)
            if f.mime_type == GOOGLE_FOLDER_MIME:
                next_path = f.full_path
                _list_children_sync(
                    service, f.id, limit=limit, path=next_path,
                    items=items, visited=visited,
                )
            else:
                items.append(f)
            if limit and len(items) >= limit:
                return
        page_token = resp.get("nextPageToken")
        if not page_token:
            return


def _list_files_sync(folder_id: str, limit: int | None = None) -> list[DriveFile]:
    """Lista arquivos recursivamente a partir da pasta raiz de conhecimento.

    A versão anterior listava apenas filhos imediatos. Se a raiz continha só
    subpastas, a sincronização pulava o acervo real. Agora a varredura percorre
    subpastas e preserva o caminho para classificação/auditoria.
    """
    service = get_drive_client()
    items: list[DriveFile] = []
    _list_children_sync(
        service, folder_id, limit=limit, path="", items=items, visited=set()
    )
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


def _extra(
    file: DriveFile,
    mime_final: str,
    ext: str,
    decisao: DriveTaxonomyDecision | None = None,
) -> dict[str, Any]:
    extra = {
        "source": "google_drive",
        "drive": {
            "file_id": file.id,
            "name": file.name,
            "path": file.path,
            "full_path": file.full_path,
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
    if decisao:
        extra["taxonomy"] = decisao.as_extra()
    return extra


def _resolver_categoria(
    categoria_base: str | None,
    decisao: DriveTaxonomyDecision,
    *,
    categorizar_automaticamente: bool,
) -> str:
    base = (categoria_base or "").strip()
    if categorizar_automaticamente and (not base or base in {"auto", "doutrina"}):
        return decisao.categoria
    return base or decisao.categoria


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


def _arquivo_auditado(f: DriveFile, allowed: set[str]) -> dict[str, Any]:
    decisao = classificar_drive_file(f.name, f.path, f.mime_type)
    indexavel = f.mime_type in allowed and not decisao.excluir
    return {
        "id": f.id,
        "name": f.name,
        "path": f.path,
        "full_path": f.full_path,
        "mime_type": f.mime_type,
        "modified_time": f.modified_time,
        "size": f.size,
        "web_view_link": f.web_view_link,
        "indexavel": indexavel,
        "categoria_sugerida": decisao.categoria,
        "confianca_sugerida": decisao.confianca,
        "prioridade": decisao.prioridade,
        "tipo_fonte": decisao.tipo_fonte,
        "area_juridica": decisao.area_juridica,
        "motivo": decisao.motivo,
        "sinais": decisao.sinais,
    }


async def listar_arquivos_pasta(folder_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    folder_id = (folder_id or knowledge_folder_id()).strip()
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID não configurado")
    files = await asyncio.to_thread(_list_files_sync, folder_id, limit)
    allowed = allowed_mime_types()
    return [_arquivo_auditado(f, allowed) for f in files]


async def auditar_pasta_conhecimento(folder_id: str | None = None, limit: int | None = None) -> dict[str, Any]:
    folder_id = (folder_id or knowledge_folder_id()).strip()
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID não configurado")
    data = await listar_arquivos_pasta(folder_id=folder_id, limit=limit)
    por_categoria: dict[str, int] = {}
    por_area: dict[str, int] = {}
    por_tipo: dict[str, int] = {}
    indexaveis = ignorados = 0
    for item in data:
        if item["indexavel"]:
            indexaveis += 1
        else:
            ignorados += 1
        por_categoria[item["categoria_sugerida"]] = por_categoria.get(item["categoria_sugerida"], 0) + 1
        area = item["area_juridica"] or "nao_identificada"
        tipo = item["tipo_fonte"] or "nao_identificado"
        por_area[area] = por_area.get(area, 0) + 1
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1

    ranking = sorted(
        data,
        key=lambda x: (x["indexavel"], x["prioridade"], x["modified_time"] or ""),
        reverse=True,
    )
    return {
        "folder_id": folder_id,
        "total": len(data),
        "indexaveis": indexaveis,
        "ignorados": ignorados,
        "por_categoria_sugerida": por_categoria,
        "por_area_juridica": por_area,
        "por_tipo_fonte": por_tipo,
        "ranking": ranking,
        "nota": (
            "Auditoria baseada em nome, caminho e MIME. A sincronização continua "
            "deduplicando/versionando por gdrive:file_id e hash de conteúdo."
        ),
    }


async def _processar_arquivo(
    db: AsyncSession,
    file: DriveFile,
    *,
    categoria: str,
    confianca: str,
    categorizar_automaticamente: bool,
) -> dict[str, Any]:
    decisao = classificar_drive_file(file.name, file.path, file.mime_type)
    if decisao.excluir:
        return {
            "file_id": file.id,
            "name": file.name,
            "path": file.path,
            "status": "ignorado",
            "categoria": decisao.categoria,
            "prioridade": decisao.prioridade,
            "motivo": decisao.motivo,
        }

    allowed = allowed_mime_types()
    if file.mime_type not in allowed:
        return {
            "file_id": file.id,
            "name": file.name,
            "path": file.path,
            "status": "ignorado",
            "categoria": decisao.categoria,
            "prioridade": decisao.prioridade,
            "motivo": f"MIME não permitido: {file.mime_type}",
        }

    if file.size and file.size > max_file_bytes():
        return {
            "file_id": file.id,
            "name": file.name,
            "path": file.path,
            "status": "ignorado",
            "categoria": decisao.categoria,
            "prioridade": decisao.prioridade,
            "motivo": f"Arquivo acima do limite: {file.size} bytes",
        }

    raw, mime_final, ext = await asyncio.to_thread(_download_drive_file_sync, file)
    if len(raw) > max_file_bytes():
        return {
            "file_id": file.id,
            "name": file.name,
            "path": file.path,
            "status": "ignorado",
            "categoria": decisao.categoria,
            "prioridade": decisao.prioridade,
            "motivo": f"Arquivo baixado acima do limite: {len(raw)} bytes",
        }

    texto_extraido = await asyncio.to_thread(_texto_de_bytes, raw, mime_final, ext)
    if len((texto_extraido or "").strip()) < 50:
        return {
            "file_id": file.id,
            "name": file.name,
            "path": file.path,
            "status": "erro",
            "categoria": decisao.categoria,
            "prioridade": decisao.prioridade,
            "motivo": "Texto extraído vazio ou insuficiente para indexação",
        }

    categoria_final = _resolver_categoria(
        categoria, decisao, categorizar_automaticamente=categorizar_automaticamente
    )
    confianca_final = decisao.confianca if categorizar_automaticamente else confianca
    extra = _extra(file, mime_final, ext, decisao)
    extra["confidence_level"] = confianca_final

    resultado = await upsert_documento(
        db,
        titulo=file.name,
        categoria=categoria_final,
        conteudo=texto_extraido,
        chave_origem=f"gdrive:{file.id}",
        fonte=file.web_view_link or f"google_drive:{file.id}",
        extra=extra,
        confianca=confianca_final,
        embutir_vetores=True,
    )
    return {
        "file_id": file.id,
        "name": file.name,
        "path": file.path,
        "full_path": file.full_path,
        "status": resultado,
        "categoria": categoria_final,
        "categoria_sugerida": decisao.categoria,
        "confianca": confianca_final,
        "prioridade": decisao.prioridade,
        "tipo_fonte": decisao.tipo_fonte,
        "area_juridica": decisao.area_juridica,
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
    categorizar_automaticamente: bool | None = None,
) -> dict[str, Any]:
    if not drive_enabled():
        raise RuntimeError("GOOGLE_DRIVE_ENABLED=false. Ative no .env para sincronizar.")

    folder_id = (folder_id or knowledge_folder_id()).strip()
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID não configurado")

    categoria = (categoria or default_categoria()).strip() or "auto"
    if categorizar_automaticamente is None:
        categorizar_automaticamente = auto_categorizar_enabled()

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
                        db,
                        file,
                        categoria=categoria,
                        confianca=confianca,
                        categorizar_automaticamente=categorizar_automaticamente,
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
                        "path": file.path,
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
                        "path": file.path,
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

        por_categoria: dict[str, int] = {}
        for item in resultados:
            cat = item.get("categoria") or item.get("categoria_sugerida") or "nao_classificado"
            por_categoria[cat] = por_categoria.get(cat, 0) + 1

        return {
            "ok": status in {"sucesso", "parcial"},
            "status": status,
            "folder_id": folder_id,
            "categoria_base": categoria,
            "categorizar_automaticamente": categorizar_automaticamente,
            "total_files_seen": seen,
            "total_files_ingested": ingested,
            "total_files_skipped": skipped,
            "por_categoria": por_categoria,
            "resultados": sorted(
                resultados,
                key=lambda x: (x.get("status") in {"novo", "atualizado", "inalterado"}, x.get("prioridade", 0)),
                reverse=True,
            ),
            "erro": erro_geral,
            "executado_em": datetime.now(timezone.utc).isoformat(),
        }


async def reindexar_arquivo(
    db: AsyncSession,
    file_id: str,
    *,
    categoria: str | None = None,
    confianca: str = "media",
    categorizar_automaticamente: bool | None = None,
) -> dict[str, Any]:
    if not drive_enabled():
        raise RuntimeError("GOOGLE_DRIVE_ENABLED=false. Ative no .env para sincronizar.")
    if categorizar_automaticamente is None:
        categorizar_automaticamente = auto_categorizar_enabled()
    file = await asyncio.to_thread(_get_file_sync, file_id)
    resultado = await _processar_arquivo(
        db,
        file,
        categoria=(categoria or default_categoria()),
        confianca=confianca,
        categorizar_automaticamente=categorizar_automaticamente,
    )
    await db.commit()
    return resultado
