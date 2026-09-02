# ── app/routers/trash.py ─────────────────────────────────────────────────────
# Lixeira: lista, restaura e purga definitivamente registros soft-deleted.
# Admin/sócio para listar/restaurar; purga irreversível é superadmin apenas.
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.client import Client
from app.models.deadline import Deadline
from app.models.document import Document
from app.models.environmental import EnvironmentalCase
from app.models.fee import Fee
from app.models.legal_doc import LegalDoc
from app.models.procuracao import Procuracao
from app.models.task import Task
from app.models.user import User
from app.services.document_rag_bridge import desativar_rag_documento
from app.services.document_storage_operation_service import (
    StorageOperationInvalidaError,
    criar_operacao_purge,
)
from app.tasks.dispatcher import agendar_purge_storage

ENTIDADES = {
    "clients": (Client, lambda x: x.nome or x.razao_social),
    "cases": (Case, lambda x: f"{x.numero_interno} {x.titulo}"),
    "deadlines": (Deadline, lambda x: x.titulo),
    "documents": (Document, lambda x: x.titulo),
    "legal_docs": (LegalDoc, lambda x: x.titulo),
    "fees": (Fee, lambda x: x.descricao),
    "procuracoes": (Procuracao, lambda x: f"Procuração {x.id[:8]}"),
    "environmental_cases": (EnvironmentalCase, lambda x: f"Auto {x.numero_auto}"),
    "tasks": (Task, lambda x: x.titulo),
}

router = APIRouter(prefix="/trash", tags=["Lixeira"])


async def _exigir_pai_ativo(db: AsyncSession, modelo, registro_id: str, rotulo: str) -> None:
    pai = await db.scalar(select(modelo).where(modelo.id == registro_id))
    if pai is None:
        raise HTTPException(status_code=409, detail=f"Não é possível restaurar: {rotulo} vinculado não existe mais.")
    if getattr(pai, "deleted_at", None) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Não é possível restaurar enquanto {rotulo} vinculado estiver na lixeira. Restaure a dependência primeiro.",
        )


async def _validar_dependencias_restauração(db: AsyncSession, entidade: str, registro) -> None:
    if entidade == "clients":
        return
    if entidade == "cases":
        client_id = getattr(registro, "client_id", None)
        if client_id:
            await _exigir_pai_ativo(db, Client, client_id, "o cliente")
        return

    case_id = getattr(registro, "case_id", None)
    if case_id:
        await _exigir_pai_ativo(db, Case, case_id, "o caso")
    client_id = getattr(registro, "client_id", None)
    if client_id:
        await _exigir_pai_ativo(db, Client, client_id, "o cliente")


@router.get("/")
async def listar(
    entidade: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    del cu
    if entidade not in ENTIDADES:
        raise HTTPException(status_code=422, detail=f"Entidade inválida. Use: {list(ENTIDADES)}")
    modelo, rotulo = ENTIDADES[entidade]
    total = int(
        await db.scalar(select(func.count()).select_from(modelo).where(modelo.deleted_at.isnot(None))) or 0
    )
    rows = (
        await db.execute(
            select(modelo)
            .where(modelo.deleted_at.isnot(None))
            .order_by(modelo.deleted_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    data = []
    for r in rows:
        item = {"id": r.id, "rotulo": rotulo(r), "excluido_em": r.deleted_at}
        if entidade == "documents":
            item.update({
                "legal_hold": bool(r.legal_hold),
                "retention_until": r.retention_until,
                "purga_bloqueada": bool(
                    r.legal_hold
                    or (r.retention_until and r.retention_until > datetime.now(timezone.utc))
                ),
            })
        data.append(item)
    return {"data": data, "total": total, "page": page, "page_size": page_size}


@router.post("/{entidade}/{registro_id}/restaurar")
async def restaurar(
    entidade: str,
    registro_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    if entidade not in ENTIDADES:
        raise HTTPException(status_code=422, detail="Entidade inválida")
    modelo, _ = ENTIDADES[entidade]
    registro = (
        await db.execute(
            select(modelo).where(modelo.id == registro_id, modelo.deleted_at.isnot(None))
        )
    ).scalar_one_or_none()
    if not registro:
        raise HTTPException(status_code=404, detail="Registro não está na lixeira")

    await _validar_dependencias_restauração(db, entidade, registro)
    excluido_em = registro.deleted_at
    registro.deleted_at = None
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "RESTORE",
        entidade,
        registro_id,
        dados_antes={"deleted_at": excluido_em.isoformat() if excluido_em else None},
        dados_depois={"deleted_at": None},
    )
    await db.commit()
    return {"detail": "Registro restaurado"}


class PurgarRequest(BaseModel):
    motivo: str = Field(..., min_length=5, max_length=500,
                        description="Motivo da purga (LGPD art. 18, VI) — obrigatório.")


@router.post("/{entidade}/{registro_id}/purgar")
async def purgar(
    entidade: str,
    registro_id: str,
    payload: PurgarRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin"])),
):
    """Hard purge governado.

    Para documentos, legal hold/retenção são gates de backend sem bypass por
    superadmin. A identidade de storage é capturada em outbox ANTES do delete e
    comitada na mesma transação; a remoção física ocorre somente depois.
    """
    if entidade not in ENTIDADES:
        raise HTTPException(status_code=422, detail="Entidade inválida")
    modelo, rotulo = ENTIDADES[entidade]
    registro = (
        await db.execute(
            select(modelo)
            .where(modelo.id == registro_id, modelo.deleted_at.isnot(None))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not registro:
        raise HTTPException(
            status_code=404,
            detail="Registro não está na lixeira — purga exige exclusão (soft delete) prévia.",
        )

    storage_operation = None
    if entidade == "documents":
        agora = datetime.now(timezone.utc)
        if bool(registro.legal_hold):
            raise HTTPException(status_code=409, detail="Documento sob legal hold — purga bloqueada")
        if registro.retention_until and registro.retention_until > agora:
            raise HTTPException(status_code=409, detail="Documento ainda está dentro do prazo de retenção")
        try:
            storage_operation = criar_operacao_purge(registro, requested_by=cu.id)
        except StorageOperationInvalidaError as exc:
            raise HTTPException(
                status_code=409,
                detail="Documento sem identidade de storage válida — correção administrativa necessária",
            ) from exc
        db.add(storage_operation)
        await desativar_rag_documento(db, registro)

    excluido_em = registro.deleted_at
    dados_antes = {"excluido_em": excluido_em.isoformat() if excluido_em else None}
    if entidade != "documents":
        dados_antes["rotulo"] = rotulo(registro)

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "PURGE",
        entidade,
        registro_id,
        detalhes=payload.motivo,
        dados_antes=dados_antes,
        dados_depois={
            "purgado": True,
            "storage_cleanup_outbox": bool(storage_operation),
        },
    )
    await db.delete(registro)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Não é possível purgar: há registros dependentes vinculados a "
                f"este {entidade[:-1] if entidade.endswith('s') else entidade}. "
                "Purgue as dependências primeiro."
            ),
        )

    mecanismo = None
    if storage_operation is not None:
        # Se o agendamento falhar depois do commit, a operação continua pendente
        # no banco e pode ser retomada; a evidência da intenção não se perde.
        try:
            mecanismo = await agendar_purge_storage(storage_operation.id, background_tasks)
        except Exception:
            mecanismo = "pending_outbox"

    return {
        "detail": "Registro purgado definitivamente",
        "storage_cleanup": mecanismo,
    }
