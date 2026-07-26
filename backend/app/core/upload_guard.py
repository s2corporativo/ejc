# ── app/core/upload_guard.py ─────────────────────────────────────────────────
# Guarda canônica de upload — teto de tamanho + assinatura de PDF, aplicada
# ANTES de qualquer parse CPU-bound (fitz/OCR). Mesmo contrato dos guards
# locais já existentes (documents.upload, rag._validar_pdf_upload,
# documento_ia.analisar): 413 para excesso de tamanho, 422 para conteúdo
# inválido. Função pura (testável sem banco); routers sem guarda própria
# devem chamar validar_upload() logo após file.read().
from __future__ import annotations

from fastapi import HTTPException

from app.core.config import get_settings


def validar_upload(
    conteudo: bytes,
    *,
    max_mb: int | None = None,
    exigir_pdf: bool = False,
) -> None:
    """Valida bytes de um upload já lido em memória.

    - 422 se vazio;
    - 413 se exceder ``max_mb`` (default: settings.MAX_UPLOAD_MB);
    - 422 se ``exigir_pdf`` e o conteúdo não começar com a assinatura %PDF-
      (magic bytes — não confiar em extensão nem content_type do cliente).
    """
    limite = max_mb if max_mb is not None else get_settings().MAX_UPLOAD_MB
    if not conteudo:
        raise HTTPException(status_code=422, detail="Arquivo vazio")
    if len(conteudo) > limite * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede o limite de {limite}MB",
        )
    if exigir_pdf and not conteudo.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=422,
            detail="Arquivo não é um PDF válido (assinatura ausente)",
        )
