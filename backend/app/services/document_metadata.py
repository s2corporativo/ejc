"""Metadados compartilhados de armazenamento; não determina acesso ao documento."""
import hashlib

from app.models.document import Document


def hash_token_data_room(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def remote_path_documento(document: Document) -> str | None:
    filepath = str(document.filepath or "")
    if not filepath.startswith("drive://"):
        return None
    candidato = filepath[len("drive://") :].strip()
    if not candidato or candidato == str(document.drive_file_id or ""):
        return None
    return candidato


def normalizar_nome_original(filename: str | None, fallback: str) -> str:
    """Apenas metadado; jamais use o nome original como destino físico."""
    nome = (filename or fallback).replace("\\", "/").rsplit("/", 1)[-1].strip()
    return (nome or fallback)[:255]
