"""Regras de negócio canônicas da entidade Processo.

Leitores devem usar `processo_principal(case_id, db)` em vez dos campos
processuais legados da tabela `cases`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case
from app.models.process import Process
from app.repositories.process_repository import process_repository
from app.schemas.process import ProcessCreate, ProcessResponse, ProcessUpdate

_JUDICIAL_TYPES = {"judicial", "recurso", "cautelar", "execucao"}


class ProcessServiceError(Exception):
    """Erro de domínio traduzido pelo router para resposta HTTP."""


class ProcessNotFound(ProcessServiceError):
    pass


class ProcessConflict(ProcessServiceError):
    pass


def _as_dict(process: Process, *, ok: bool | None = None) -> dict[str, Any]:
    data = ProcessResponse.model_validate(process).model_dump()
    if ok is not None:
        data["ok"] = ok
    return data


async def obter_processo(db: AsyncSession, process_id: str) -> Process:
    process = await process_repository.get(db, process_id)
    if process is None:
        raise ProcessNotFound("Processo não encontrado")
    return process


async def _validate_parent(
    db: AsyncSession,
    case_id: str,
    parent_id: str | None,
    process_id: str | None = None,
) -> Process | None:
    if not parent_id:
        return None
    if process_id and parent_id == process_id:
        raise ProcessConflict("Um processo não pode ser acessório de si próprio")
    parent = await process_repository.get(db, parent_id)
    if parent is None or parent.case_id != case_id:
        raise ProcessConflict("Processo principal informado não pertence ao mesmo caso")
    if parent.status == "arquivado":
        raise ProcessConflict("Processo arquivado não pode receber acessórios")
    return parent


async def _set_principal(db: AsyncSession, process: Process) -> None:
    if process.status == "arquivado":
        raise ProcessConflict("Processo arquivado não pode ser principal")
    await process_repository.clear_principal(db, process.case_id)
    process.is_principal = True
    process.processo_principal_id = None
    await db.flush()


async def _sync_case_legacy(db: AsyncSession, process: Process) -> None:
    """Write-through temporário para consumidores ainda ligados a `cases`."""
    if not process.is_principal:
        return
    await db.execute(
        update(Case)
        .where(Case.id == process.case_id, Case.deleted_at.is_(None))
        .values(
            numero_processo=process.numero_cnj,
            tribunal=process.tribunal,
            comarca=process.comarca,
            vara=process.vara,
            valor_causa=process.valor_causa,
            has_judicial_process=(process.tipo in _JUDICIAL_TYPES),
        )
    )


async def listar_processos(
    case_id: str,
    db: AsyncSession,
    archive_filter: str = "ativos",
) -> list[dict[str, Any]]:
    rows = await process_repository.list_for_case(db, case_id, archive_filter)
    return [_as_dict(row) for row in rows]


async def criar_processo(
    case_id: str,
    payload: ProcessCreate,
    db: AsyncSession,
) -> dict[str, Any]:
    parent = await _validate_parent(db, case_id, payload.processo_principal_id)
    if payload.status == "arquivado" and payload.is_principal:
        raise ProcessConflict("Processo criado como arquivado não pode ser principal")
    if payload.processo_principal_id and payload.is_principal:
        raise ProcessConflict("Processo acessório não pode ser marcado como principal")

    current_principal = await process_repository.principal(db, case_id)
    if parent is not None and current_principal is None:
        await _set_principal(db, parent)
        await _sync_case_legacy(db, parent)
        current_principal = parent

    should_be_principal = (
        payload.status != "arquivado"
        and payload.processo_principal_id is None
        and (payload.is_principal is True or current_principal is None)
    )
    process = Process(
        id=str(uuid4()),
        case_id=case_id,
        **payload.model_dump(exclude={"is_principal"}),
        is_principal=False,
    )
    db.add(process)
    await db.flush()
    if should_be_principal:
        await _set_principal(db, process)
    await _sync_case_legacy(db, process)
    await db.flush()
    return _as_dict(process)


async def atualizar_processo(
    process_id: str,
    payload: ProcessUpdate,
    db: AsyncSession,
) -> dict[str, Any]:
    process = await obter_processo(db, process_id)
    changes = payload.model_dump(exclude_unset=True)
    requested_principal = changes.pop("is_principal", None)

    requested_status = changes.get("status")
    if requested_status == "arquivado" and process.status != "arquivado":
        raise ProcessConflict("Use a ação específica de arquivamento")
    if process.status == "arquivado" and requested_status not in {None, "arquivado"}:
        raise ProcessConflict("Use a ação específica de desarquivamento")

    parent = await _validate_parent(
        db,
        process.case_id,
        changes.get("processo_principal_id"),
        process.id,
    )
    if requested_principal is True and parent is not None:
        raise ProcessConflict("Processo acessório não pode ser marcado como principal")

    for field, value in changes.items():
        setattr(process, field, value)

    if requested_principal is True:
        await _set_principal(db, process)
    elif requested_principal is False and process.is_principal:
        replacement = await process_repository.first_active_except(
            db,
            process.case_id,
            process.id,
        )
        if replacement is None:
            raise ProcessConflict("O único processo ativo do caso deve permanecer principal")
        process.is_principal = False
        await _set_principal(db, replacement)
        await _sync_case_legacy(db, replacement)

    await _sync_case_legacy(db, process)
    await db.flush()
    return _as_dict(process, ok=True)


async def promover_principal(process_id: str, db: AsyncSession) -> dict[str, Any]:
    process = await obter_processo(db, process_id)
    await _set_principal(db, process)
    await _sync_case_legacy(db, process)
    await db.flush()
    return _as_dict(process, ok=True)


async def arquivar_processo(
    process_id: str,
    motivo: str | None,
    db: AsyncSession,
) -> dict[str, Any]:
    process = await obter_processo(db, process_id)
    if process.status == "arquivado":
        raise ProcessConflict("Processo já arquivado")

    was_principal = process.is_principal
    process.status = "arquivado"
    process.archived_at = datetime.now(timezone.utc)
    process.archive_reason = (motivo or "").strip() or None
    process.is_principal = False

    if was_principal:
        replacement = await process_repository.first_active_except(
            db,
            process.case_id,
            process.id,
        )
        if replacement is not None:
            await _set_principal(db, replacement)
            await _sync_case_legacy(db, replacement)

    await db.flush()
    return _as_dict(process, ok=True)


async def desarquivar_processo(process_id: str, db: AsyncSession) -> dict[str, Any]:
    process = await obter_processo(db, process_id)
    if process.status != "arquivado":
        raise ProcessConflict("Processo não está arquivado")

    process.status = "ativo"
    process.archived_at = None
    process.archive_reason = None
    if await process_repository.principal(db, process.case_id) is None:
        await _set_principal(db, process)
        await _sync_case_legacy(db, process)

    await db.flush()
    return _as_dict(process, ok=True)


async def remover_processo(process_id: str, db: AsyncSession) -> dict[str, Any]:
    process = await obter_processo(db, process_id)
    was_principal = process.is_principal
    process.deleted_at = datetime.now(timezone.utc)
    process.is_principal = False

    if was_principal:
        replacement = await process_repository.first_active_except(
            db,
            process.case_id,
            process.id,
        )
        if replacement is not None:
            await _set_principal(db, replacement)
            await _sync_case_legacy(db, replacement)

    await db.flush()
    return {"ok": True, "case_id": process.case_id}


async def processo_principal(case_id: str, db: AsyncSession) -> dict | None:
    process = await process_repository.principal(db, case_id)
    return _as_dict(process) if process else None


async def numero_processo_efetivo(
    case_id: str,
    db: AsyncSession,
    fallback: str | None = None,
) -> str | None:
    process = await processo_principal(case_id, db)
    if process and process.get("numero_cnj"):
        return process["numero_cnj"]
    return fallback
