"""Vinculação posterior de um lote universal a um caso recém-criado."""
from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user
from app.models.case import CaseMovimento
from app.models.document import Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem
from app.models.user import User
from app.routers.entrada_universal import _acesso_batch

router = APIRouter(prefix="/entrada-universal", tags=["Entrada Universal de Documentos"])
settings = get_settings()


class VincularCasoRequest(BaseModel):
    case_id: str


def _sha256_arquivo(filepath: str | None) -> str | None:
    if not filepath:
        return None
    absoluto = os.path.join(settings.UPLOAD_DIR, filepath)
    if not os.path.isfile(absoluto):
        return None
    digest = hashlib.sha256()
    try:
        with open(absoluto, "rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _duplicata_tecnica_recente(documento: Document, item: DocumentIntakeItem, cu: User) -> bool:
    """Restringe a limpeza à cópia criada pelo fluxo legado poucos minutos antes."""
    criado = documento.created_at
    if criado is None:
        return False
    if criado.tzinfo is None:
        criado = criado.replace(tzinfo=timezone.utc)
    return bool(
        documento.uploaded_by == cu.id
        and documento.filename == item.filename
        and int(documento.size_bytes or 0) == int(item.size_bytes or 0)
        and criado >= datetime.now(timezone.utc) - timedelta(minutes=15)
    )


def _clonar_documento_local(documento: Document, caso_id: str, client_id: str | None, cu: User) -> Document:
    if documento.drive_file_id or not documento.filepath:
        raise OSError("Documento externo não pode ser clonado automaticamente")
    origem = os.path.join(settings.UPLOAD_DIR, documento.filepath)
    if not os.path.isfile(origem):
        raise OSError("Arquivo físico original não encontrado")
    ext = os.path.splitext(documento.filename or documento.filepath)[1].lower()
    agora = datetime.now(timezone.utc)
    subdir = f"{agora.year}/{agora.month:02d}"
    os.makedirs(os.path.join(settings.UPLOAD_DIR, subdir), exist_ok=True)
    novo_id = str(uuid4())
    relativo = f"{subdir}/{novo_id}{ext}"
    shutil.copy2(origem, os.path.join(settings.UPLOAD_DIR, relativo))
    return Document(
        id=novo_id,
        titulo=documento.titulo,
        descricao=(documento.descricao or "") + " | cópia isolada pela Entrada Universal",
        tipo=documento.tipo,
        filename=documento.filename,
        filepath=relativo,
        mimetype=documento.mimetype,
        size_bytes=documento.size_bytes,
        ocr_text=documento.ocr_text,
        confidencialidade=documento.confidencialidade,
        case_id=caso_id,
        client_id=client_id,
        uploaded_by=cu.id,
    )


@router.post("/{batch_id}/vincular-caso")
async def vincular_lote_ao_caso(
    batch_id: str,
    req: VincularCasoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Vincula lote e originais a um caso, sem mover documento de outro caso."""
    batch = await _acesso_batch(db, cu, batch_id)
    caso = await verificar_acesso_caso(db, cu, req.case_id)

    if batch.case_id and batch.case_id != req.case_id:
        raise HTTPException(
            status_code=409,
            detail="Este lote já está vinculado a outro caso e não pode ser movimentado automaticamente.",
        )

    lote_ja_vinculado = batch.case_id == req.case_id
    pares = (
        await db.execute(
            select(DocumentIntakeItem, Document)
            .join(Document, Document.id == DocumentIntakeItem.document_id)
            .where(DocumentIntakeItem.batch_id == batch.id, Document.deleted_at.is_(None))
            .order_by(DocumentIntakeItem.source_order)
        )
    ).all()

    ids_lote = {documento.id for _, documento in pares}
    existentes_stmt = select(Document).where(
        Document.case_id == caso.id,
        Document.deleted_at.is_(None),
    )
    if ids_lote:
        existentes_stmt = existentes_stmt.where(Document.id.notin_(ids_lote))
    existentes = (await db.execute(existentes_stmt)).scalars().all()
    existentes_por_sha: dict[str, list[Document]] = {}
    for documento in existentes:
        digest = _sha256_arquivo(documento.filepath)
        if digest:
            existentes_por_sha.setdefault(digest, []).append(documento)

    vinculados = 0
    ja_vinculados = 0
    duplicatas_tecnicas_removidas = 0
    copias_isoladas = 0
    conflitos: list[dict[str, str]] = []
    vistos: set[str] = set()
    for item, documento in pares:
        if item.id in vistos:
            continue
        vistos.add(item.id)

        if documento.case_id is None:
            for duplicata in existentes_por_sha.get(item.sha256, []):
                if duplicata.deleted_at is None and _duplicata_tecnica_recente(duplicata, item, cu):
                    duplicata.deleted_at = datetime.now(timezone.utc)
                    duplicatas_tecnicas_removidas += 1
            documento.case_id = caso.id
            documento.client_id = caso.client_id
            vinculados += 1
        elif documento.case_id == caso.id:
            ja_vinculados += 1
        else:
            try:
                clone = _clonar_documento_local(documento, caso.id, caso.client_id, cu)
                db.add(clone)
                await db.flush()
                item.document_id = clone.id
                item.duplicate_of_document_id = documento.id
                copias_isoladas += 1
                vinculados += 1
            except OSError as exc:
                conflitos.append({
                    "document_id": documento.id,
                    "filename": documento.filename,
                    "motivo": str(exc),
                })

    batch.case_id = caso.id
    batch.client_id = caso.client_id

    if not lote_ja_vinculado or vinculados or conflitos or duplicatas_tecnicas_removidas:
        descricao = (
            f"Entrada Universal vinculada ao caso. Lote: {batch.id}. "
            f"Documentos vinculados: {vinculados}; já vinculados: {ja_vinculados}; "
            f"duplicatas técnicas removidas: {duplicatas_tecnicas_removidas}; "
            f"cópias isoladas entre casos: {copias_isoladas}; conflitos preservados: {len(conflitos)}. "
            "Classificação, prazos e estratégia permanecem sujeitos à revisão humana."
        )
        db.add(CaseMovimento(
            id=str(uuid4()),
            case_id=caso.id,
            tipo="ia",
            descricao=descricao[:8000],
            created_by=cu.id,
        ))
    await db.commit()

    return {
        "ok": True,
        "batch_id": batch.id,
        "case_id": caso.id,
        "documentos_vinculados": vinculados,
        "documentos_ja_vinculados": ja_vinculados,
        "duplicatas_tecnicas_removidas": duplicatas_tecnicas_removidas,
        "copias_isoladas": copias_isoladas,
        "conflitos": conflitos,
        "operacao_idempotente": lote_ja_vinculado and vinculados == 0 and not conflitos,
        "revisao_obrigatoria": True,
    }
