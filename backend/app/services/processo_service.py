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
from app.services.validators_service import normalizar_cnj

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


def _legacy_text(value: str | None, max_length: int) -> str | None:
    """Adapta somente o espelho legado, sem truncar o dado canônico.

    `processes` usa larguras maiores que `cases` para tribunal/comarca/vara.
    O write-through não pode transformar um dado válido no domínio canônico em
    erro de banco por estouro de varchar na tabela legada.
    """
    if value is None:
        return None
    return value[:max_length]


async def _garantir_cnj_no_mesmo_caso(
    db: AsyncSession, case_id: str, numero_cnj: str | None
) -> None:
    """Um CNJ pode ter vários registros/graus, mas pertence a um só Caso.

    O lock consultivo por CNJ fecha a corrida entre duas criações em casos
    diferentes. Registros soft-deleted também bloqueiam criação silenciosa:
    devem ser restaurados/reconciliados para preservar a trilha de auditoria.
    """
    numero_norm = normalizar_cnj(numero_cnj or "")
    if len(numero_norm) != 20:
        return
    await process_repository.lock_cnj(db, numero_norm)
    case_ids = await process_repository.case_ids_for_cnj(db, numero_norm)
    outros = [cid for cid in case_ids if cid != case_id]
    if outros:
        raise ProcessConflict(
            "CNJ já vinculado a outro caso do EJC. Restaure ou reconcilie o "
            "registro existente em vez de criar duplicidade."
        )


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
    """Write-through temporário para consumidores ainda ligados a `cases`.

    A fonte de verdade é `processes`; esta função será removida somente quando o
    inventário confirmar ausência de leitores dos campos processuais legados.
    As larguras menores do legado são respeitadas sem modificar o valor integral
    armazenado em `processes`.
    """
    if not process.is_principal:
        return
    await db.execute(
        update(Case)
        .where(Case.id == process.case_id, Case.deleted_at.is_(None))
        .values(
            numero_processo=_legacy_text(process.numero_cnj, 30),
            tribunal=_legacy_text(process.tribunal, 20),
            comarca=_legacy_text(process.comarca, 100),
            vara=_legacy_text(process.vara, 100),
            valor_causa=process.valor_causa,
            has_judicial_process=(process.tipo in _JUDICIAL_TYPES),
        )
    )


async def _clear_case_legacy(db: AsyncSession, case_id: str) -> None:
    """Limpa o espelho quando o caso deixa de possuir processo principal."""
    await db.execute(
        update(Case)
        .where(Case.id == case_id, Case.deleted_at.is_(None))
        .values(
            numero_processo=None,
            tribunal=None,
            comarca=None,
            vara=None,
            valor_causa=None,
            has_judicial_process=False,
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
    await process_repository.lock_case(db, case_id)
    await _garantir_cnj_no_mesmo_caso(db, case_id, payload.numero_cnj)
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
    if payload.status == "arquivado":
        process.archived_at = datetime.now(timezone.utc)
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
    await process_repository.lock_case(db, process.case_id)
    changes = payload.model_dump(exclude_unset=True)
    if "numero_cnj" in changes:
        await _garantir_cnj_no_mesmo_caso(db, process.case_id, changes.get("numero_cnj"))
    requested_principal = changes.pop("is_principal", None)

    requested_status = changes.get("status")
    if requested_status == "arquivado" and process.status != "arquivado":
        raise ProcessConflict("Use a ação específica de arquivamento")
    if process.status == "arquivado" and requested_status not in {None, "arquivado"}:
        raise ProcessConflict("Use a ação específica de desarquivamento")

    parent_requested = "processo_principal_id" in changes
    parent = await _validate_parent(
        db,
        process.case_id,
        changes.get("processo_principal_id"),
        process.id,
    )
    if requested_principal is True and parent is not None:
        raise ProcessConflict("Processo acessório não pode ser marcado como principal")
    if (
        process.is_principal
        and parent_requested
        and parent is not None
        and requested_principal is not False
    ):
        raise ProcessConflict(
            "Para vincular o processo principal como acessório, informe is_principal=false"
        )

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
    await process_repository.lock_case(db, process.case_id)
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
    await process_repository.lock_case(db, process.case_id)
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
        else:
            await _clear_case_legacy(db, process.case_id)

    await db.flush()
    return _as_dict(process, ok=True)


async def desarquivar_processo(process_id: str, db: AsyncSession) -> dict[str, Any]:
    process = await obter_processo(db, process_id)
    await process_repository.lock_case(db, process.case_id)
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
    await process_repository.lock_case(db, process.case_id)
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
        else:
            await _clear_case_legacy(db, process.case_id)

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
