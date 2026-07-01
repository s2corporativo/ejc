"""
documento_ia.py — Importação inteligente de documentos.
POST /api/documentos-ia/analisar  (multipart: file)
  → OCR + extração estruturada + diagnóstico jurídico + honorários + referências.
Retorna JSON que o frontend usa para pré-preencher um novo caso (sem duplicar a
criação de casos — usa o /cases existente).
"""
import os
import tempfile
import logging

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import documento_service

logger = logging.getLogger("ejc.documento_ia")
router = APIRouter(prefix="/documentos-ia", tags=["Importação Inteligente"])

MAX_BYTES = 25 * 1024 * 1024  # 25 MB
TIPOS_OK = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "image/png", "image/jpeg", "image/jpg", "image/tiff", "image/webp",
}


@router.post("/analisar")
async def analisar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload de PDF/DOCX/imagem → análise jurídica estruturada (HITL)."""
    mimetype = file.content_type or ""
    if mimetype not in TIPOS_OK:
        # alguns navegadores mandam octet-stream; deixamos o OCR decidir pela extensão
        if not (file.filename or "").lower().endswith((".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tiff", ".webp")):
            raise HTTPException(415, "Formato não suportado. Envie PDF, DOCX ou imagem.")

    conteudo = await file.read()
    if len(conteudo) > MAX_BYTES:
        raise HTTPException(413, "Arquivo muito grande (máx. 25 MB).")
    if not conteudo:
        raise HTTPException(400, "Arquivo vazio.")

    # Validação por magic bytes (server-side) — reusa a barreira do GED. Não
    # confiar em content_type/extensão. Extensões sem mapa (.tiff/.webp) passam
    # pelo fallback e ainda assim têm o MIME real detectado; .pdf/.docx/.png/.jpg
    # ganham verificação estrita de conteúdo.
    sufixo = os.path.splitext(file.filename or "doc")[1] or ".bin"
    from app.routers.documents import _validar_conteudo
    mime_real = _validar_conteudo(sufixo.lower(), conteudo)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=sufixo)
    try:
        tmp.write(conteudo)
        tmp.flush()
        tmp.close()
        resultado = await documento_service.extrair_e_analisar(
            tmp.name, mime_real or mimetype or None, db=db, enriquecer_rag=True
        )
        if not resultado.get("ok"):
            raise HTTPException(422, resultado.get("erro", "Falha ao processar documento."))
        return resultado
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
