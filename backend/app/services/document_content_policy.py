"""Política canônica de validação de conteúdo para ingestão documental.

A validação de extensão/MIME é regra de domínio de ingestão, não responsabilidade
HTTP. Centralizá-la aqui elimina a dependência invertida ``service -> router`` e
permite que GED, Portal, Raio-X e Sala compartilhem exatamente a mesma política.
"""
from __future__ import annotations

from pathlib import Path

import magic
from fastapi import HTTPException

EXTENSOES_PERMITIDAS: set[str] = {
    ".pdf",
    ".docx",
    ".doc",
    ".jpg",
    ".jpeg",
    ".png",
    ".xlsx",
    ".xls",
    ".txt",
    ".xml",
}

# ``python-magic`` pode identificar OOXML como ZIP porque DOCX/XLSX são
# contêineres ZIP. Esses MIME permanecem explicitamente aceitos; nenhum MIME
# fornecido pelo cliente participa da decisão.
MIME_POR_EXTENSAO: dict[str, frozenset[str]] = {
    ".pdf": frozenset({"application/pdf"}),
    ".docx": frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
        }
    ),
    ".doc": frozenset({"application/msword", "application/x-ole-storage"}),
    ".xlsx": frozenset(
        {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/zip",
        }
    ),
    ".xls": frozenset({"application/vnd.ms-excel", "application/x-ole-storage"}),
    ".jpg": frozenset({"image/jpeg"}),
    ".jpeg": frozenset({"image/jpeg"}),
    ".png": frozenset({"image/png"}),
    ".xml": frozenset({"application/xml", "text/xml", "text/plain"}),
}


def extensao_normalizada(filename: str | None) -> str:
    """Retorna somente o sufixo normalizado; nome do cliente nunca vira path."""

    return Path(filename or "").suffix.lower()


def exigir_extensao_permitida(filename: str | None) -> str:
    """Valida a allowlist e retorna a extensão normalizada."""

    ext = extensao_normalizada(filename)
    if ext not in EXTENSOES_PERMITIDAS:
        raise HTTPException(status_code=422, detail=f"Extensão não permitida: {ext}")
    return ext


def validar_conteudo(ext: str, conteudo: bytes) -> str:
    """Valida magic bytes e devolve o MIME derivado do conteúdo.

    A leitura de apenas 2 KiB para detecção mantém custo de memória O(1) neste
    passo. O limite/streaming do arquivo completo pertence ao serviço de ingestão.
    """

    ext = (ext or "").lower()
    mime_real = magic.from_buffer(conteudo[:2048], mime=True)
    esperados = MIME_POR_EXTENSAO.get(ext)
    if esperados is None:
        # TXT tem detecção ambígua entre text/plain e variantes charset-aware.
        return mime_real or "text/plain"
    if mime_real not in esperados:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Conteúdo do arquivo ({mime_real}) não corresponde à extensão {ext}."
            ),
        )
    return mime_real
