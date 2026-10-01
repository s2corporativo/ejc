"""Integração canônica de comprovantes financeiros com o GED."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit_log import criar_audit_log
from app.models.document import DocConfidencialidade, Document
from app.models.user import User
from app.services.document_access_policy import pode_acessar_confidencialidade


@dataclass(frozen=True, slots=True)
class ArquivoFinanceiroGED:
    documento: Document
    caminho_absoluto: Path


async def exigir_documento_financeiro(
    db: AsyncSession,
    user: User,
    document_id: str,
    *,
    case_id: str | None = None,
    client_id: str | None = None,
) -> Document:
    """Valida documento ativo, cofre e contexto antes de gravar uma FK financeira."""
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Documento não encontrado")
    if not pode_acessar_confidencialidade(user, doc.confidencialidade):
        raise HTTPException(403, "Documento restrito — acesso negado")
    if case_id and doc.case_id and str(doc.case_id) != str(case_id):
        raise HTTPException(409, "Documento pertence a outro caso")
    if client_id and doc.client_id and str(doc.client_id) != str(client_id):
        raise HTTPException(409, "Documento pertence a outro cliente")
    return doc


async def preparar_extrato_no_ged(
    db: AsyncSession,
    user: User,
    *,
    conteudo: bytes,
    filename: str,
    mimetype: str | None,
    formato: str,
    case_id: str | None,
    client_id: str | None,
) -> ArquivoFinanceiroGED:
    """Grava o original do extrato no storage GED e adiciona Document à UoW.

    O caller deve remover ``caminho_absoluto`` se a transação for revertida.
    """
    settings = get_settings()
    doc_id = str(uuid4())
    agora = datetime.now(timezone.utc)
    ext = "." + formato.lower().lstrip(".")
    if ext not in {".pdf", ".ofx", ".csv"}:
        raise HTTPException(422, "Formato de extrato não suportado pelo GED")
    rel = Path("financeiro") / "extratos" / str(agora.year) / f"{agora.month:02d}" / f"{doc_id}{ext}"
    full = (Path(settings.UPLOAD_DIR).resolve() / rel).resolve()
    raiz = Path(settings.UPLOAD_DIR).resolve()
    try:
        full.relative_to(raiz)
    except ValueError as exc:
        raise HTTPException(500, "Destino documental inválido") from exc
    full.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(full, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(conteudo)
    except BaseException:
        try:
            full.unlink()
        except FileNotFoundError:
            pass
        raise

    nome = Path((filename or f"extrato{ext}").replace("\\", "/")).name[:255]
    doc = Document(
        id=doc_id,
        titulo=nome or f"extrato{ext}",
        descricao="Extrato bancário importado para conciliação financeira",
        tipo="comprovante_financeiro",
        filename=nome or f"extrato{ext}",
        filepath=rel.as_posix(),
        mimetype=mimetype or {
            ".pdf": "application/pdf",
            ".ofx": "application/x-ofx",
            ".csv": "text/csv",
        }[ext],
        size_bytes=len(conteudo),
        sha256=hashlib.sha256(conteudo).hexdigest(),
        confidencialidade=DocConfidencialidade.interno,
        case_id=case_id,
        client_id=client_id,
        uploaded_by=user.id,
        versao=1,
        versao_grupo_id=doc_id,
    )
    db.add(doc)
    await criar_audit_log(
        db, user.id, user.role.value, "UPLOAD", "documents", doc_id,
        detalhes="Extrato bancário armazenado no GED para conciliação",
        dados_depois={
            "tipo": "comprovante_financeiro",
            "case_id": case_id,
            "client_id": client_id,
            "sha256": doc.sha256,
            "size_bytes": len(conteudo),
        },
    )
    return ArquivoFinanceiroGED(documento=doc, caminho_absoluto=full)
