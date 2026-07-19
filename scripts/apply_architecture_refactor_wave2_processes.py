#!/usr/bin/env python3
"""Onda 2: torna Processo um domínio com schema, repositório e serviço próprios."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_new(relative: str, content: str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Arquivo novo já existe com conteúdo divergente: {relative}")
        return
    path.write_text(content, encoding="utf-8")


def replace_managed(relative: str, content: str, required_markers: tuple[str, ...]) -> None:
    path = ROOT / relative
    current = path.read_text(encoding="utf-8")
    if current == content:
        return
    if not all(marker in current for marker in required_markers):
        missing = [marker for marker in required_markers if marker not in current]
        raise RuntimeError(f"Contrato inesperado em {relative}; marcadores ausentes: {missing}")
    path.write_text(content, encoding="utf-8")


PROCESS_SCHEMA = '''"""Contratos de entrada e saída da entidade Processo."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_PROCESS_STATUS = {"ativo", "suspenso", "encerrado", "arquivado"}
_PROCESS_TYPES = {"judicial", "administrativo", "arbitral", "outro"}


def _validate_process_number(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > 30:
        raise ValueError("Número do processo deve ter no máximo 30 caracteres")
    from app.services.validators_service import normalizar_cnj, validar_cnj

    if len(normalizar_cnj(value)) == 20 and not validar_cnj(value):
        raise ValueError("Número CNJ inválido: dígito verificador não confere")
    return value


class ProcessCreate(BaseModel):
    numero_cnj: Optional[str] = None
    instancia: Optional[str] = Field(default=None, max_length=20)
    tribunal: Optional[str] = Field(default=None, max_length=160)
    comarca: Optional[str] = Field(default=None, max_length=160)
    vara: Optional[str] = Field(default=None, max_length=160)
    classe: Optional[str] = Field(default=None, max_length=160)
    fase: Optional[str] = Field(default=None, max_length=40)
    tipo: str = "judicial"
    processo_principal_id: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    status: str = "ativo"
    is_principal: Optional[bool] = None

    @field_validator("numero_cnj")
    @classmethod
    def validate_number(cls, value: Optional[str]) -> Optional[str]:
        return _validate_process_number(value)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in _PROCESS_STATUS:
            raise ValueError(f"Status inválido. Use um de {sorted(_PROCESS_STATUS)}")
        return value

    @field_validator("tipo")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in _PROCESS_TYPES:
            raise ValueError(f"Tipo inválido. Use um de {sorted(_PROCESS_TYPES)}")
        return value


class ProcessUpdate(BaseModel):
    numero_cnj: Optional[str] = None
    instancia: Optional[str] = Field(default=None, max_length=20)
    tribunal: Optional[str] = Field(default=None, max_length=160)
    comarca: Optional[str] = Field(default=None, max_length=160)
    vara: Optional[str] = Field(default=None, max_length=160)
    classe: Optional[str] = Field(default=None, max_length=160)
    fase: Optional[str] = Field(default=None, max_length=40)
    tipo: Optional[str] = None
    processo_principal_id: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    status: Optional[str] = None
    is_principal: Optional[bool] = None

    @field_validator("numero_cnj")
    @classmethod
    def validate_number(cls, value: Optional[str]) -> Optional[str]:
        return _validate_process_number(value)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in _PROCESS_STATUS:
            raise ValueError(f"Status inválido. Use um de {sorted(_PROCESS_STATUS)}")
        return value

    @field_validator("tipo")
    @classmethod
    def validate_type(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in _PROCESS_TYPES:
            raise ValueError(f"Tipo inválido. Use um de {sorted(_PROCESS_TYPES)}")
        return value


class ProcessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    numero_cnj: Optional[str] = None
    instancia: Optional[str] = None
    tribunal: Optional[str] = None
    comarca: Optional[str] = None
    vara: Optional[str] = None
    classe: Optional[str] = None
    fase: Optional[str] = None
    tipo: str
    processo_principal_id: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    status: str
    is_principal: bool
    archived_at: Optional[datetime] = None
    archive_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ArchiveProcessRequest(BaseModel):
    motivo: Optional[str] = Field(default=None, max_length=1000)
'''

PROCESS_REPOSITORY = '''"""Persistência canônica da entidade Processo."""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.process import Process


class ProcessRepository:
    async def list_for_case(
        self, db: AsyncSession, case_id: str, archive_filter: str = "ativos"
    ) -> Sequence[Process]:
        query = select(Process).where(Process.case_id == case_id, Process.deleted_at.is_(None))
        if archive_filter == "ativos":
            query = query.where(Process.status != "arquivado")
        elif archive_filter == "arquivados":
            query = query.where(Process.status == "arquivado")
        query = query.order_by(Process.is_principal.desc(), Process.created_at.asc())
        return (await db.execute(query)).scalars().all()

    async def get(self, db: AsyncSession, process_id: str) -> Process | None:
        return (
            await db.execute(
                select(Process).where(Process.id == process_id, Process.deleted_at.is_(None))
            )
        ).scalar_one_or_none()

    async def principal(self, db: AsyncSession, case_id: str) -> Process | None:
        return (
            await db.execute(
                select(Process)
                .where(
                    Process.case_id == case_id,
                    Process.is_principal.is_(True),
                    Process.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    async def first_active_except(
        self, db: AsyncSession, case_id: str, excluded_id: str
    ) -> Process | None:
        return (
            await db.execute(
                select(Process)
                .where(
                    Process.case_id == case_id,
                    Process.id != excluded_id,
                    Process.status != "arquivado",
                    Process.deleted_at.is_(None),
                )
                .order_by(Process.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def clear_principal(self, db: AsyncSession, case_id: str) -> None:
        await db.execute(
            update(Process)
            .where(
                Process.case_id == case_id,
                Process.is_principal.is_(True),
                Process.deleted_at.is_(None),
            )
            .values(is_principal=False)
        )


process_repository = ProcessRepository()
'''

PROCESS_SERVICE = '''"""Regras de negócio canônicas da entidade Processo.

Leitores devem usar `processo_principal(case_id, db)` em vez dos campos
processuais legados da tabela `cases`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case
from app.models.process import Process
from app.repositories.process_repository import process_repository
from app.schemas.process import ProcessCreate, ProcessResponse, ProcessUpdate


class ProcessServiceError(Exception):
    pass


class ProcessNotFound(ProcessServiceError):
    pass


class ProcessConflict(ProcessServiceError):
    pass


def _as_dict(process: Process) -> dict[str, Any]:
    return ProcessResponse.model_validate(process).model_dump()


async def _require_process(db: AsyncSession, process_id: str) -> Process:
    process = await process_repository.get(db, process_id)
    if process is None:
        raise ProcessNotFound("Processo não encontrado")
    return process


async def _validate_parent(
    db: AsyncSession, case_id: str, parent_id: str | None, process_id: str | None = None
) -> None:
    if not parent_id:
        return
    if process_id and parent_id == process_id:
        raise ProcessConflict("Um processo não pode ser acessório de si próprio")
    parent = await process_repository.get(db, parent_id)
    if parent is None or parent.case_id != case_id:
        raise ProcessConflict("Processo principal informado não pertence ao mesmo caso")


async def _set_principal(db: AsyncSession, process: Process) -> None:
    await process_repository.clear_principal(db, process.case_id)
    await db.flush()
    process.is_principal = True
    process.processo_principal_id = None


async def _sync_case_legacy(db: AsyncSession, process: Process) -> None:
    """Write-through temporário para consumidores ainda ligados a `cases`.

    A fonte de verdade é `processes`; esta função poderá ser removida quando o
    inventário confirmar que nenhum leitor usa os campos legados.
    """
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
            has_judicial_process=(process.tipo == "judicial"),
        )
    )


async def listar_processos(
    case_id: str, db: AsyncSession, archive_filter: str = "ativos"
) -> list[dict[str, Any]]:
    rows = await process_repository.list_for_case(db, case_id, archive_filter)
    return [_as_dict(row) for row in rows]


async def criar_processo(
    case_id: str, payload: ProcessCreate, db: AsyncSession
) -> dict[str, Any]:
    await _validate_parent(db, case_id, payload.processo_principal_id)
    current_principal = await process_repository.principal(db, case_id)
    should_be_principal = payload.is_principal is True or current_principal is None

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
    process_id: str, payload: ProcessUpdate, db: AsyncSession
) -> dict[str, Any]:
    process = await _require_process(db, process_id)
    changes = payload.model_dump(exclude_unset=True)
    requested_principal = changes.pop("is_principal", None)
    await _validate_parent(
        db, process.case_id, changes.get("processo_principal_id"), process.id
    )
    for field, value in changes.items():
        setattr(process, field, value)
    if requested_principal is True:
        await _set_principal(db, process)
    elif requested_principal is False and process.is_principal:
        replacement = await process_repository.first_active_except(db, process.case_id, process.id)
        if replacement is None:
            raise ProcessConflict("O único processo ativo do caso deve permanecer principal")
        process.is_principal = False
        await _set_principal(db, replacement)
        await _sync_case_legacy(db, replacement)
    if process.status == "arquivado":
        process.archived_at = process.archived_at or datetime.now(timezone.utc)
    else:
        process.archived_at = None
        process.archive_reason = None
    await _sync_case_legacy(db, process)
    await db.flush()
    return _as_dict(process)


async def promover_principal(process_id: str, db: AsyncSession) -> dict[str, Any]:
    process = await _require_process(db, process_id)
    if process.status == "arquivado":
        raise ProcessConflict("Processo arquivado não pode ser principal")
    await _set_principal(db, process)
    await _sync_case_legacy(db, process)
    await db.flush()
    return _as_dict(process)


async def arquivar_processo(
    process_id: str, motivo: str | None, db: AsyncSession
) -> dict[str, Any]:
    process = await _require_process(db, process_id)
    if process.status == "arquivado":
        raise ProcessConflict("Processo já arquivado")
    was_principal = process.is_principal
    process.status = "arquivado"
    process.archived_at = datetime.now(timezone.utc)
    process.archive_reason = (motivo or "").strip() or None
    process.is_principal = False
    if was_principal:
        replacement = await process_repository.first_active_except(db, process.case_id, process.id)
        if replacement is not None:
            await _set_principal(db, replacement)
            await _sync_case_legacy(db, replacement)
    await db.flush()
    return _as_dict(process)


async def desarquivar_processo(process_id: str, db: AsyncSession) -> dict[str, Any]:
    process = await _require_process(db, process_id)
    if process.status != "arquivado":
        raise ProcessConflict("Processo não está arquivado")
    process.status = "ativo"
    process.archived_at = None
    process.archive_reason = None
    if await process_repository.principal(db, process.case_id) is None:
        await _set_principal(db, process)
        await _sync_case_legacy(db, process)
    await db.flush()
    return _as_dict(process)


async def remover_processo(process_id: str, db: AsyncSession) -> dict[str, Any]:
    process = await _require_process(db, process_id)
    was_principal = process.is_principal
    process.deleted_at = datetime.now(timezone.utc)
    process.is_principal = False
    if was_principal:
        replacement = await process_repository.first_active_except(db, process.case_id, process.id)
        if replacement is not None:
            await _set_principal(db, replacement)
            await _sync_case_legacy(db, replacement)
    await db.flush()
    return {"ok": True, "case_id": process.case_id}


async def processo_principal(case_id: str, db: AsyncSession) -> dict | None:
    process = await process_repository.principal(db, case_id)
    return _as_dict(process) if process else None


async def numero_processo_efetivo(
    case_id: str, db: AsyncSession, fallback: str | None = None
) -> str | None:
    process = await processo_principal(case_id, db)
    return process.get("numero_cnj") if process and process.get("numero_cnj") else fallback
'''

PROCESS_ROUTER = '''"""Processos — entidade independente do Caso (1 Caso : N Processos).

O router trata HTTP, ownership e auditoria. Persistência e regras de principal,
arquivamento e compatibilidade legada vivem no domínio `processo_service`.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user, require_roles
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.schemas.process import ArchiveProcessRequest, ProcessCreate, ProcessUpdate
from app.services import processo_service

router = APIRouter(tags=["Processos"])
_ESCRITA = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar"]


def _http_error(exc: processo_service.ProcessServiceError) -> HTTPException:
    if isinstance(exc, processo_service.ProcessNotFound):
        return HTTPException(404, str(exc))
    return HTTPException(409, str(exc))


async def _case_id(process_id: str, db: AsyncSession) -> str:
    try:
        process = await processo_service._require_process(db, process_id)
    except processo_service.ProcessServiceError as exc:
        raise _http_error(exc) from exc
    return process.case_id


@router.get("/cases/{case_id}/processes")
async def listar_processos(
    case_id: str,
    arquivo: str = Query("ativos", pattern="^(ativos|arquivados|todos)$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    data = await processo_service.listar_processos(case_id, db, arquivo)
    return {"data": data}


@router.post("/cases/{case_id}/processes", status_code=201)
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
        db, cu.id, cu.role.value, "CREATE", "processes", result["id"],
        dados_depois={"case_id": case_id, "is_principal": result["is_principal"]},
    )
    await db.commit()
    return result


@router.patch("/processes/{process_id}")
async def atualizar_processo(
    process_id: str,
    body: ProcessUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id(process_id, db)
    await verificar_acesso_caso(db, cu, case_id)
    try:
        result = await processo_service.atualizar_processo(process_id, body, db)
    except processo_service.ProcessServiceError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    await criar_audit_log(
        db, cu.id, cu.role.value, "UPDATE", "processes", process_id,
        dados_depois={key: str(value) for key, value in body.model_dump(exclude_unset=True).items()},
    )
    await db.commit()
    return result


@router.post("/processes/{process_id}/principal")
async def definir_principal(
    process_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id(process_id, db)
    await verificar_acesso_caso(db, cu, case_id)
    try:
        result = await processo_service.promover_principal(process_id, db)
    except processo_service.ProcessServiceError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    await criar_audit_log(
        db, cu.id, cu.role.value, "SET_PRINCIPAL", "processes", process_id,
        dados_depois={"is_principal": True},
    )
    await db.commit()
    return result


@router.post("/processes/{process_id}/arquivar")
async def arquivar_processo(
    process_id: str,
    body: ArchiveProcessRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id(process_id, db)
    await verificar_acesso_caso(db, cu, case_id)
    try:
        result = await processo_service.arquivar_processo(
            process_id, body.motivo if body else None, db
        )
    except processo_service.ProcessServiceError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    await criar_audit_log(
        db, cu.id, cu.role.value, "ARCHIVE", "processes", process_id,
        dados_depois={"status": "arquivado", "motivo": (body.motivo if body else None) or ""},
    )
    await db.commit()
    return result


@router.post("/processes/{process_id}/desarquivar")
async def desarquivar_processo(
    process_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id(process_id, db)
    await verificar_acesso_caso(db, cu, case_id)
    try:
        result = await processo_service.desarquivar_processo(process_id, db)
    except processo_service.ProcessServiceError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    await criar_audit_log(
        db, cu.id, cu.role.value, "UNARCHIVE", "processes", process_id,
        dados_depois={"status": "ativo"},
    )
    await db.commit()
    return result


@router.delete("/processes/{process_id}")
async def remover_processo(
    process_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id(process_id, db)
    await verificar_acesso_caso(db, cu, case_id)
    try:
        result = await processo_service.remover_processo(process_id, db)
    except processo_service.ProcessServiceError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "processes", process_id)
    await db.commit()
    return result
'''

PROCESS_TESTS = '''from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.process import ProcessCreate, ProcessUpdate


def test_process_schema_accepts_administrative_identifier():
    payload = ProcessCreate(numero_cnj="SEI-12345/2026", tipo="administrativo")
    assert payload.numero_cnj == "SEI-12345/2026"


def test_process_schema_rejects_invalid_cnj_check_digit():
    with pytest.raises(ValidationError):
        ProcessCreate(numero_cnj="0000000-00.0000.0.00.0000")


def test_process_update_preserves_unset_fields():
    payload = ProcessUpdate(status="suspenso")
    assert payload.model_dump(exclude_unset=True) == {"status": "suspenso"}


def test_router_does_not_embed_sql_rules():
    source = (Path(__file__).parents[1] / "app/routers/processes.py").read_text(encoding="utf-8")
    assert "sqlalchemy import text" not in source
    assert "INSERT INTO processes" not in source
    assert '@router.get("/cases/{case_id}/processes")' in source
    assert '@router.post("/processes/{process_id}/principal")' in source


def test_service_preserves_legacy_accessors():
    source = (Path(__file__).parents[1] / "app/services/processo_service.py").read_text(encoding="utf-8")
    assert "async def processo_principal" in source
    assert "async def numero_processo_efetivo" in source
    assert "_sync_case_legacy" in source
'''


def main() -> int:
    write_new("backend/app/schemas/process.py", PROCESS_SCHEMA)
    write_new("backend/app/repositories/process_repository.py", PROCESS_REPOSITORY)
    write_new("backend/tests/test_process_contracts.py", PROCESS_TESTS)
    replace_managed(
        "backend/app/services/processo_service.py",
        PROCESS_SERVICE,
        ("Accessor canonico", "async def processo_principal", "async def numero_processo_efetivo"),
    )
    replace_managed(
        "backend/app/routers/processes.py",
        PROCESS_ROUTER,
        ("Processos — entidade independente", "class ProcessoIn", "@router.get"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
