# ── app/services/upload_lote_service.py ──────────────────────────────────────
"""Validação e gravação compartilhada de lotes de upload.

Raio-X e Sala Jurídica usam este serviço para as etapas que precisam ter a
mesma implementação de segurança: teto do lote, allowlist de extensão, tamanho,
SHA-256/deduplicação, validação de conteúdo real e gravação confinada em
``UPLOAD_DIR``. Construção das entidades, extração/OCR e auditoria permanecem
nos chamadores porque têm semânticas diferentes.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

settings = get_settings()


@dataclass
class ArquivoValidado:
    """Arquivo que passou nas checagens e já foi gravado no storage."""

    nome_original: str
    ext: str
    mimetype: str
    size_bytes: int
    sha256: str
    filepath: str
    ocr_utilizado: bool


EXTENSOES_OCR = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".webp"}


def _segmento_storage(valor: str, *, campo: str) -> str:
    """Aceita somente um segmento simples e nunca ``.``/``..``."""
    if not isinstance(valor, str):
        raise ValueError(f"{campo} inválido para gravação em disco")
    segmento = Path(valor).name
    if (
        not segmento
        or segmento in {".", ".."}
        or segmento != valor
        or Path(valor).is_absolute()
    ):
        raise ValueError(f"{campo} inválido para gravação em disco")
    return segmento


def _destino_confinado(root: Path, rel: Path) -> Path:
    """Resolve o destino e prova que ele continua sob a raiz configurada."""
    raiz = root.resolve()
    destino = (raiz / rel).resolve()
    try:
        destino.relative_to(raiz)
    except ValueError as exc:
        raise ValueError("destino de upload escapou da raiz configurada") from exc
    return destino


async def processar_lote(
    files: list[UploadFile],
    *,
    max_arquivos: int,
    extensoes_permitidas: set[str],
    existing_hashes: set[str],
    storage_subdir: str,
    entidade_id: str,
) -> tuple[list[ArquivoValidado], list[str], list[dict[str, str]]]:
    """Valida e grava o lote, preservando o contrato fail-soft por arquivo.

    O teto do lote é erro de requisição (422). Violações individuais geram
    entrada em ``erros``/``duplicados`` e não abortam os demais arquivos.
    ``existing_hashes`` é atualizado somente após gravação bem-sucedida.
    """
    if not files or len(files) > max_arquivos:
        raise HTTPException(422, f"Envie de 1 a {max_arquivos} arquivos por lote")

    subdir_seguro = _segmento_storage(storage_subdir, campo="storage_subdir")
    entidade_segura = _segmento_storage(entidade_id, campo="entidade_id")
    raiz_upload = Path(settings.UPLOAD_DIR)

    from app.routers.documents import _validar_conteudo

    validos: list[ArquivoValidado] = []
    duplicados: list[str] = []
    erros: list[dict[str, str]] = []

    for upload in files:
        filename = Path(upload.filename or "documento").name[:255]
        ext = Path(filename).suffix.lower()
        if ext not in extensoes_permitidas:
            erros.append({"arquivo": filename, "erro": "Formato não suportado"})
            continue

        content = await upload.read()
        if not content:
            erros.append({"arquivo": filename, "erro": "Arquivo vazio"})
            continue
        if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
            erros.append(
                {"arquivo": filename, "erro": f"Excede {settings.MAX_UPLOAD_MB} MB"}
            )
            continue

        digest = hashlib.sha256(content).hexdigest()
        if digest in existing_hashes:
            duplicados.append(filename)
            continue

        try:
            mime_real = _validar_conteudo(ext, content)
        except HTTPException as exc:
            erros.append({"arquivo": filename, "erro": str(exc.detail)[:300]})
            continue

        now = datetime.now(timezone.utc)
        rel = (
            Path(subdir_seguro)
            / f"{now.year}"
            / f"{now.month:02d}"
            / entidade_segura
            / f"{uuid4()}{ext}"
        )
        full = _destino_confinado(raiz_upload, rel)
        full.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(full, "wb") as target:
            await target.write(content)

        existing_hashes.add(digest)
        validos.append(
            ArquivoValidado(
                nome_original=filename,
                ext=ext,
                mimetype=mime_real,
                size_bytes=len(content),
                sha256=digest,
                filepath=str(rel),
                ocr_utilizado=ext in EXTENSOES_OCR,
            )
        )

    return validos, duplicados, erros
