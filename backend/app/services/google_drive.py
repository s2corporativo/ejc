"""Google Drive service — upload, download, delete de documentos.

Autenticação: rclone (OAuth2, token renovado automaticamente).
O rclone deve estar configurado em /root/.config/rclone/rclone.conf
com o remote [gdrive]. O token é gerenciado pelo rclone.
"""
import io
import os
import json
import logging
import tempfile
import subprocess
from typing import Optional

logger = logging.getLogger("ejc.drive")

RCLONE_REMOTE   = "gdrive"
RCLONE_CONF     = os.getenv("RCLONE_CONFIG", "/opt/ejc/config/rclone.conf")
# Pasta base no Drive para documentos do EJC
BASE_FOLDER     = "EJC-Documentos"
RCLONE_TIMEOUT  = 120  # segundos por operação

# Mapeamento de folder_id (env var) → subfolder no Drive
# Os IDs antigos (service account) são ignorados; usamos nomes de pastas
_FOLDER_NAMES: dict[str, str] = {
    os.getenv("DRIVE_FOLDER_CASOS",       "__casos__"):       "casos",
    os.getenv("DRIVE_FOLDER_PECAS",       "__pecas__"):       "pecas",
    os.getenv("DRIVE_FOLDER_CONTRATOS",   "__contratos__"):   "contratos",
    os.getenv("DRIVE_FOLDER_CLIENTES",    "__clientes__"):    "clientes",
    os.getenv("DRIVE_FOLDER_HONORARIOS",  "__honorarios__"):  "honorarios",
    os.getenv("DRIVE_FOLDER_COMPROVANTES","__comprovantes__"):"comprovantes",
    os.getenv("DRIVE_FOLDER_TEMPLATES",   "__templates__"):   "templates",
    os.getenv("DRIVE_FOLDER_BACKUP",      "__backup__"):      "backups",
}

DRIVE_AVAILABLE = os.path.exists(RCLONE_CONF) and bool(
    subprocess.run(["which", "rclone"], capture_output=True).returncode == 0
)


def _subfolder(folder_id: Optional[str]) -> str:
    """Converte folder_id (env var) em nome de subpasta legível."""
    if folder_id and folder_id in _FOLDER_NAMES:
        return _FOLDER_NAMES[folder_id]
    return "geral"


def _rclone_path(subfolder: str, filename: str = "") -> str:
    base = f"{RCLONE_REMOTE}:{BASE_FOLDER}/{subfolder}"
    return f"{base}/{filename}" if filename else base


def _run(cmd: list[str], timeout: int = RCLONE_TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def upload_file(
    content: bytes,
    filename: str,
    mime_type: str,
    folder_id: Optional[str] = None,
) -> dict:
    """Faz upload de bytes para o Drive. Retorna {id, name, webViewLink, webContentLink}."""
    if not DRIVE_AVAILABLE:
        raise RuntimeError("rclone não configurado — execute: rclone config create gdrive drive")

    subfolder = _subfolder(folder_id)
    dest_path  = _rclone_path(subfolder)
    dest_file  = _rclone_path(subfolder, filename)

    # Garantir que a subpasta existe
    _run(["rclone", "mkdir", dest_path])

    # Escrever bytes em arquivo temporário e fazer upload
    with tempfile.NamedTemporaryFile(delete=False, suffix="_" + filename) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        r = _run(["rclone", "copyto", tmp_path, dest_file])
        if r.returncode != 0:
            raise RuntimeError(f"rclone upload: {r.stderr[:300]}")
    finally:
        os.unlink(tmp_path)

    # Obter ID do arquivo no Drive via lsjson
    r2 = _run(["rclone", "lsjson", dest_path, "--include", filename])
    file_id = ""
    if r2.returncode == 0 and r2.stdout.strip():
        try:
            entries = json.loads(r2.stdout)
            if entries:
                file_id = entries[0].get("ID", "")
        except Exception:
            pass

    return {
        "id": file_id,
        "name": filename,
        "webViewLink":    f"https://drive.google.com/file/d/{file_id}/view" if file_id else "",
        "webContentLink": f"https://drive.google.com/uc?id={file_id}" if file_id else "",
    }


def get_file_link(file_id: str) -> dict:
    """Retorna metadados de um arquivo pelo ID do Drive."""
    if not file_id:
        return {"id": "", "name": "", "webViewLink": "", "webContentLink": "", "size": 0}
    return {
        "id":             file_id,
        "name":           "",
        "webViewLink":    f"https://drive.google.com/file/d/{file_id}/view",
        "webContentLink": f"https://drive.google.com/uc?id={file_id}",
        "size":           0,
    }


def download_file(file_id: str) -> tuple[bytes, str]:
    """Baixa o conteúdo de um arquivo pelo ID do Drive."""
    if not DRIVE_AVAILABLE:
        raise RuntimeError("rclone não configurado")
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
    try:
        r = _run(["rclone", "copyto", f"gdrive:--drive-root-folder-id={file_id}", tmp_path], timeout=60)
        if r.returncode != 0:
            # fallback: download via drive ID direto
            r2 = _run(["rclone", "cat", f"gdrive:{file_id}"], timeout=60)
            if r2.returncode == 0:
                return r2.stdout.encode(), "application/octet-stream"
            raise RuntimeError(f"rclone download: {r.stderr[:200]}")
        with open(tmp_path, "rb") as f:
            return f.read(), "application/octet-stream"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def delete_file(file_id: str) -> None:
    """Remove um arquivo do Drive pelo ID."""
    if not DRIVE_AVAILABLE or not file_id:
        return
    # rclone não suporta delete por ID diretamente; operação best-effort
    logger.warning(f"[Drive] delete_file({file_id}): não suportado via rclone por ID — ignored")
