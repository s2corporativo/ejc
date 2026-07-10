from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin, require_roles
from app.models.audit_log import criar_audit_log
from app.models.system_module_setting import SystemModuleSetting
from app.models.user import User
from app.schemas.system_module_settings import (
    SystemModuleSettingList,
    SystemModuleSettingResponse,
    SystemModuleSettingUpdate,
)

router = APIRouter(prefix="/system-modules", tags=["Lifecycle de Módulos"])

_internal_users = require_roles(
    [
        "superadmin",
        "admin",
        "socio",
        "advogado",
        "advogado_auxiliar",
        "estagiario",
        "secretaria",
        "financeiro",
    ]
)

PROTECTED_MODULE_KEYS = {
    "dashboard",
    "configuracoes",
    "usuarios",
    "auditoria",
    "mapa-modulos",
}
MODULE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,99}$")


def _role_value(user: User) -> str:
    return str(getattr(user.role, "value", user.role))


def _validate_module_key(module_key: str) -> str:
    normalized = module_key.strip().lower()
    if not MODULE_KEY_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="Chave de módulo inválida")
    return normalized


@router.get("/settings", response_model=SystemModuleSettingList)
async def listar_module_settings(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_internal_users),
):
    rows = (
        await db.execute(
            select(SystemModuleSetting).order_by(SystemModuleSetting.module_key)
        )
    ).scalars().all()
    return SystemModuleSettingList(
        data=[SystemModuleSettingResponse.model_validate(row) for row in rows],
        total=len(rows),
        protected_module_keys=sorted(PROTECTED_MODULE_KEYS),
        notice=(
            "Feature flags controlam disponibilidade e navegação, mas não concedem "
            "autorização. O RBAC do backend permanece obrigatório."
        ),
    )


@router.put(
    "/settings/{module_key}", response_model=SystemModuleSettingResponse
)
async def salvar_module_setting(
    module_key: str,
    payload: SystemModuleSettingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_admin),
):
    module_key = _validate_module_key(module_key)
    if module_key in PROTECTED_MODULE_KEYS and (
        not payload.enabled or not payload.menu_visible or payload.status != "active"
    ):
        raise HTTPException(
            status_code=409,
            detail="Módulo estrutural protegido não pode ser ocultado ou desabilitado.",
        )

    row = (
        await db.execute(
            select(SystemModuleSetting).where(
                SystemModuleSetting.module_key == module_key
            )
        )
    ).scalar_one_or_none()
    values = payload.model_dump()
    if row is None:
        row = SystemModuleSetting(
            module_key=module_key,
            updated_by=cu.id,
            **values,
        )
        db.add(row)
        action = "MODULE_SETTING_CREATED"
    else:
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_by = cu.id
        row.updated_at = datetime.now(timezone.utc)
        action = "MODULE_SETTING_UPDATED"

    await criar_audit_log(
        db,
        cu.id,
        _role_value(cu),
        action,
        "system_module_settings",
        module_key,
        detalhes=(
            f"enabled={payload.enabled};menu_visible={payload.menu_visible};"
            f"status={payload.status};replacement={payload.replacement_route or '-'}"
        ),
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(row)
    return SystemModuleSettingResponse.model_validate(row)


@router.delete("/settings/{module_key}")
async def remover_module_setting(
    module_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_admin),
):
    module_key = _validate_module_key(module_key)
    row = (
        await db.execute(
            select(SystemModuleSetting).where(
                SystemModuleSetting.module_key == module_key
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Override de módulo não encontrado")

    await db.delete(row)
    await criar_audit_log(
        db,
        cu.id,
        _role_value(cu),
        "MODULE_SETTING_RESET",
        "system_module_settings",
        module_key,
        detalhes="Override removido; manifesto frontend volta a ser o padrão.",
        ip=request.client.host if request.client else None,
    )
    await db.commit()
    return {"detail": "Override removido."}
