# ── app/services/upload_lote_service.py ──────────────────────────────────────
"""Validação e gravação de lote de upload — extraído de raio_x.py e
legal_chat.py, que tinham a mesma sequência de checagens byte-a-byte
duplicada (achado F2 do plano de fusão Casos/Raio-X/Sala Jurídica).

O que é compartilhado: teto de arquivos por lote, extensão permitida, leitura
e teto de tamanho, hash SHA-256 com deduplicação, validação de conteúdo real
(magic bytes) via `app.routers.documents._validar_conteudo`, e gravação em
disco sob um caminho `{subdir}/{ano}/{mes}/{entidade_id}/{uuid}{ext}`.

O que continua em cada chamador, de propósito (diferença legítima de
comportamento, não duplicação): construir a linha do banco (`RaioXDocumento`
vs `LegalChatAttachment`), decidir se a extração roda inline ou em fila
assíncrona, e o audit log específico do módulo.
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
    """Um arquivo do lote que passou em todas as checagens e já está em disco."""

    nome_original: str
    ext: str
    content: bytes
    mimetype: str
    size_bytes: int
    sha256: str
    filepath: str
    ocr_utilizado: bool


#: Extensões cujo conteúdo se beneficia de OCR na extração — mesmo conjunto
#: usado hoje por raio_x.py e legal_chat.py.
EXTENSOES_OCR = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".webp"}


async def processar_lote(
    files: list[UploadFile],
    *,
    max_arquivos: int,
    extensoes_permitidas: set[str],
    existing_hashes: set[str],
    storage_subdir: str,
    entidade_id: str,
) -> tuple[list[ArquivoValidado], list[str], list[dict[str, str]]]:
    """Valida e grava em disco o lote. Levanta 422 no teto de arquivos (erro de
    requisição); demais violações são fail-soft — cada arquivo é aceito,
    duplicado ou rejeitado individualmente, e o lote sempre termina 200 com o
    resultado por arquivo (mesmo contrato dos dois chamadores originais).

    `existing_hashes` é mutado com os hashes dos arquivos aceitos, para que o
    chamador possa reusá-lo em chamadas subsequentes sem reconsultar o banco.
    """
    if not files or len(files) > max_arquivos:
        raise HTTPException(422, f"Envie de 1 a {max_arquivos} arquivos por lote")

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
            erros.append({"arquivo": filename, "erro": f"Excede {settings.MAX_UPLOAD_MB} MB"})
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
            Path(storage_subdir)
            / f"{now.year}"
            / f"{now.month:02d}"
            / entidade_id
            / f"{uuid4()}{ext}"
        )
        full = Path(settings.UPLOAD_DIR) / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(full, "wb") as target:
            await target.write(content)

        existing_hashes.add(digest)
        validos.append(
            ArquivoValidado(
                nome_original=filename,
                ext=ext,
                content=content,
                mimetype=mime_real,
                size_bytes=len(content),
                sha256=digest,
                filepath=str(rel),
                ocr_utilizado=ext in EXTENSOES_OCR,
            )
        )

    return validos, duplicados, erros
