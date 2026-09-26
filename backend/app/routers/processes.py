"""Processos — entidade independente do Caso (1 Caso : N Processos).

O router trata apenas HTTP, ownership, auditoria e transação. Persistência e
regras de principal, acessórios e arquivamento vivem em `processo_service`.
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user, require_roles
from app.models.audit_log import criar_audit_log
from app.models.case import CaseMovimento
from app.models.user import User
from app.schemas.process import ArchiveProcessRequest, ProcessCreate, ProcessUpdate
from app.services import processo_service

router = APIRouter(prefix="/processes", tags=["Processos"])
casos_router = APIRouter(prefix="", tags=["Processos — Casos"])
_ESCRITA = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar"]


def _http_error(exc: processo_service.ProcessServiceError) -> HTTPException:
    if isinstance(exc, processo_service.ProcessNotFound):
        return HTTPException(404, str(exc))
    return HTTPException(409, str(exc))


async def _case_id_do_processo(db: AsyncSession, pid: str) -> str:
    try:
        process = await processo_service.obter_processo(db, pid)
    except processo_service.ProcessServiceError as exc:
        raise _http_error(exc) from exc
    return process.case_id


@casos_router.get("/cases/{case_id}/processes")
async def listar_processos(
    case_id: str,
    arquivo: str = Query("ativos", pattern="^(ativos|arquivados|todos)$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    data = await processo_service.listar_processos(case_id, db, arquivo)
    return {"data": data}


@casos_router.post("/cases/{case_id}/processes", status_code=201)
async def criar_processo(
    case_id: str,
    body: ProcessCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    await verificar_acesso_caso(db, cu, case_id)
    try:
        result = await processo_service.criar_processo(case_id, body, db)
    except processo_service.ProcessServiceError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "processes",
        result["id"],
        dados_depois={
            "case_id": case_id,
            "is_principal": result["is_principal"],
            "numero_cnj": result.get("numero_cnj"),
            "origem": "cadastro_processual",
        },
    )
    db.add(CaseMovimento(
        id=str(uuid4()),
        case_id=case_id,
        tipo="nota",
        descricao=(
            f"Processo {result.get('numero_cnj') or result['id']} vinculado ao caso. "
            "Origem: cadastro processual confirmado pelo usuário."
        ),
        created_by=cu.id,
    ))
    await db.commit()
    return result


@router.patch("/{pid}")
async def atualizar_processo(
    pid: str,
    body: ProcessUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id_do_processo(db, pid)
    await verificar_acesso_caso(db, cu, case_id)
    try:
        result = await processo_service.atualizar_processo(pid, body, db)
    except processo_service.ProcessServiceError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPDATE",
        "processes",
        pid,
        dados_depois={
            key: str(value)
            for key, value in body.model_dump(exclude_unset=True).items()
        },
    )
    await db.commit()
    return result


@router.post("/{pid}/principal")
async def definir_principal(
    pid: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id_do_processo(db, pid)
    await verificar_acesso_caso(db, cu, case_id)
    try:
        result = await processo_service.promover_principal(pid, db)
    except processo_service.ProcessServiceError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "SET_PRINCIPAL",
        "processes",
        pid,
        dados_depois={"is_principal": True},
    )
    await db.commit()
    return result


@router.post("/{pid}/arquivar")
async def arquivar_processo(
    pid: str,
    body: ArchiveProcessRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id_do_processo(db, pid)
    await verificar_acesso_caso(db, cu, case_id)
    try:
        result = await processo_service.arquivar_processo(
            pid,
            body.motivo if body else None,
            db,
        )
    except processo_service.ProcessServiceError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "ARCHIVE",
        "processes",
        pid,
        dados_depois={
            "status": "arquivado",
            "motivo": (body.motivo if body else None) or "",
        },
    )
    await db.commit()
    return result


@router.post("/{pid}/desarquivar")
async def desarquivar_processo(
    pid: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id_do_processo(db, pid)
    await verificar_acesso_caso(db, cu, case_id)
    try:
        result = await processo_service.desarquivar_processo(pid, db)
    except processo_service.ProcessServiceError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UNARCHIVE",
        "processes",
        pid,
        dados_depois={"status": "ativo"},
    )
    await db.commit()
    return result


@router.delete("/{pid}")
async def remover_processo(
    pid: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id_do_processo(db, pid)
    await verificar_acesso_caso(db, cu, case_id)
    try:
        result = await processo_service.remover_processo(pid, db)
    except processo_service.ProcessServiceError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "processes", pid)
    await db.commit()
    return result
