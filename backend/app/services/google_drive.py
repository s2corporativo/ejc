"""Google Drive storage adapter baseado exclusivamente em rclone.

O módulo é deliberadamente SÍNCRONO: chamadas a subprocesso devem ser feitas
por ``asyncio.to_thread`` na camada assíncrona. Isso mantém o adapter simples e
impede que um ``subprocess.run`` bloqueie o event loop do FastAPI.

Documentos novos persistem ``remote_path`` no GED e, por isso, download/delete
são endereçados diretamente. A resolução recursiva por ID existe somente como
fallback de compatibilidade para registros legados que não guardavam o path.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import PurePosixPath
from typing import Optional
from uuid import UUID

logger = logging.getLogger("ejc.drive")

RCLONE_REMOTE = "gdrive"
RCLONE_CONF = os.getenv("RCLONE_CONFIG", "/opt/ejc/config/rclone.conf")
BASE_FOLDER = "EJC-Documentos"
RCLONE_TIMEOUT = 120

_FOLDER_NAMES: dict[str, str] = {
    os.getenv("DRIVE_FOLDER_CASOS", "__casos__"): "casos",
    os.getenv("DRIVE_FOLDER_PECAS", "__pecas__"): "pecas",
    os.getenv("DRIVE_FOLDER_CONTRATOS", "__contratos__"): "contratos",
    os.getenv("DRIVE_FOLDER_CLIENTES", "__clientes__"): "clientes",
    os.getenv("DRIVE_FOLDER_HONORARIOS", "__honorarios__"): "honorarios",
    os.getenv("DRIVE_FOLDER_COMPROVANTES", "__comprovantes__"): "comprovantes",
    os.getenv("DRIVE_FOLDER_TEMPLATES", "__templates__"): "templates",
    os.getenv("DRIVE_FOLDER_BACKUP", "__backup__"): "backups",
}

DRIVE_AVAILABLE = os.path.exists(RCLONE_CONF) and shutil.which("rclone") is not None


class DriveIndisponivelError(RuntimeError):
    """Storage remoto indisponível ou não configurado."""


class DriveObjetoNaoEncontradoError(FileNotFoundError):
    """Objeto remoto não localizado no caminho/ID informado."""


def case_folder_token(case_id: str) -> str:
    """Token interno determinístico para ``casos/<uuid>``.

    O valor nunca vem do cliente HTTP: é construído a partir do ID de caso já
    autorizado. Validar como UUID evita criar segmentos arbitrários no remote.
    """

    try:
        normalizado = str(UUID(str(case_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("case_id inválido para storage remoto") from exc
    return f"case:{normalizado}"


def _subfolder(folder_id: Optional[str]) -> str:
    if folder_id and folder_id.startswith("case:"):
        return f"casos/{case_folder_token(folder_id[5:])[5:]}"
    if folder_id and folder_id in _FOLDER_NAMES:
        return _FOLDER_NAMES[folder_id]
    return "geral"


def _nome_remoto_seguro(filename: str) -> str:
    """Reduz filename a um único segmento sem controles."""

    nome = PurePosixPath((filename or "documento").replace("\\", "/")).name
    nome = "".join(ch for ch in nome if ch >= " " and ch != "\x7f").strip()
    if not nome or nome in {".", ".."}:
        return "documento"
    return nome[:255]


def _remote_rel_seguro(remote_path: str) -> str:
    """Valida path relativo persistido antes de interpolá-lo no remote rclone."""

    bruto = str(remote_path or "").strip().replace("\\", "/")
    path = PurePosixPath(bruto)
    if not bruto or path.is_absolute() or any(p in {"", ".", ".."} for p in path.parts):
        raise ValueError("remote_path inválido")
    if ":" in bruto:
        raise ValueError("remote_path não pode conter ':'")
    return str(path)


def _rclone_path(subfolder: str, filename: str = "") -> str:
    base = f"{RCLONE_REMOTE}:{BASE_FOLDER}/{_remote_rel_seguro(subfolder)}"
    return f"{base}/{_nome_remoto_seguro(filename)}" if filename else base


def _rclone_path_rel(remote_path: str) -> str:
    return f"{RCLONE_REMOTE}:{BASE_FOLDER}/{_remote_rel_seguro(remote_path)}"


def _run(cmd: list[str], timeout: int = RCLONE_TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Executa rclone sem shell e com timeout duro."""

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _exigir_disponivel() -> None:
    if not DRIVE_AVAILABLE:
        raise DriveIndisponivelError("Google Drive/rclone não configurado")


def upload_file(
    content: bytes,
    filename: str,
    mime_type: str,
    folder_id: Optional[str] = None,
) -> dict:
    """Faz upload de bytes e devolve ID + path remoto persistível.

    ``mime_type`` permanece no contrato porque o GED é a fonte do MIME validado;
    o rclone não precisa desse valor para a cópia atual.
    """

    del mime_type
    _exigir_disponivel()

    subfolder = _subfolder(folder_id)
    nome = _nome_remoto_seguro(filename)
    dest_dir = _rclone_path(subfolder)
    dest_file = _rclone_path(subfolder, nome)

    mkdir = _run(["rclone", "mkdir", dest_dir])
    if mkdir.returncode != 0:
        raise RuntimeError(f"rclone mkdir falhou: {mkdir.stderr[:300]}")

    suffix = PurePosixPath(nome).suffix[:16]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        copied = _run(["rclone", "copyto", tmp_path, dest_file])
        if copied.returncode != 0:
            raise RuntimeError(f"rclone upload falhou: {copied.stderr[:300]}")
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass

    # O objeto é conhecido pelo path exato; --stat evita listar a pasta inteira.
    stat = _run(["rclone", "lsjson", dest_file, "--stat"])
    if stat.returncode != 0:
        raise RuntimeError(f"rclone lsjson --stat falhou: {stat.stderr[:300]}")
    try:
        info = json.loads(stat.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("rclone lsjson --stat devolveu JSON inválido") from exc

    file_id = str(info.get("ID") or "")
    remote_path = f"{subfolder}/{nome}"
    return {
        "id": file_id,
        "name": nome,
        "remote_path": remote_path,
        "webViewLink": (
            f"https://drive.google.com/file/d/{file_id}/view" if file_id else ""
        ),
        "webContentLink": (
            f"https://drive.google.com/uc?id={file_id}" if file_id else ""
        ),
    }


def get_file_link(file_id: str) -> dict:
    """Monta links a partir do ID já persistido, sem I/O remoto."""

    if not file_id:
        return {
            "id": "",
            "webViewLink": "",
            "webContentLink": "",
        }
    return {
        "id": file_id,
        "webViewLink": f"https://drive.google.com/file/d/{file_id}/view",
        "webContentLink": f"https://drive.google.com/uc?id={file_id}",
    }


def _resolver_path_por_id(file_id: str) -> str:
    """Fallback LEGADO O(N) para registros sem ``remote_path`` persistido."""

    _exigir_disponivel()
    if not file_id:
        raise ValueError("file_id vazio")
    base = f"{RCLONE_REMOTE}:{BASE_FOLDER}"
    result = _run(["rclone", "lsjson", "-R", "--files-only", base])
    if result.returncode != 0:
        raise RuntimeError(
            f"rclone lsjson legado falhou para ID {file_id}: {result.stderr[:200]}"
        )
    try:
        entries = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("rclone lsjson legado devolveu JSON inválido") from exc
    alvo = next((entry for entry in entries if entry.get("ID") == file_id), None)
    if alvo is None:
        raise DriveObjetoNaoEncontradoError(
            f"Arquivo ID {file_id} não encontrado em {BASE_FOLDER}"
        )
    path = str(alvo.get("Path") or "")
    if not path:
        raise DriveObjetoNaoEncontradoError("Objeto remoto sem Path")
    return _rclone_path_rel(path)


def _resolver_objeto(file_id: str, remote_path: Optional[str]) -> str:
    if remote_path:
        return _rclone_path_rel(remote_path)
    return _resolver_path_por_id(file_id)


def download_file(
    file_id: str,
    *,
    remote_path: Optional[str] = None,
) -> bytes:
    """Baixa objeto por path O(1); ID recursivo só para legado."""

    _exigir_disponivel()
    src = _resolver_objeto(file_id, remote_path)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
    try:
        result = _run(["rclone", "copyto", src, tmp_path])
        if result.returncode != 0:
            stderr = result.stderr[:300]
            raise DriveObjetoNaoEncontradoError(
                f"Falha ao baixar objeto remoto: {stderr}"
            )
        with open(tmp_path, "rb") as handle:
            return handle.read()
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


def delete_file(
    file_id: str,
    *,
    remote_path: Optional[str] = None,
) -> None:
    """Remove objeto remoto; nunca converte falha em sucesso silencioso."""

    _exigir_disponivel()
    dest = _resolver_objeto(file_id, remote_path)
    result = _run(["rclone", "deletefile", dest])
    if result.returncode != 0:
        raise RuntimeError(f"rclone deletefile falhou: {result.stderr[:300]}")
    logger.info("[Drive] objeto removido do storage remoto")
