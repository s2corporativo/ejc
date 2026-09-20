from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import require_admin, require_roles
from app.models.redesign import ModuleHelp
from app.models.user import User
from app.services.integration_status import build_integration_status
from app.services.integration_runtime_status import coletar_estados_operacionais
from app.services import credential_vault_service
from app.services.module_registry import gerar_mapa_modulos, resumir_mapa_modulos

router = APIRouter(prefix="/system-modules", tags=["Mapa de Modulos"])

_gestores = require_roles(["superadmin", "admin", "socio"])


def _coletar_rotas_api(app: Any | None) -> list[dict[str, Any]]:
    if app is None:
        return []
    rotas: list[dict[str, Any]] = []
    for route in getattr(app, "routes", []) or []:
        path = getattr(route, "path", "") or ""
        if not path.startswith("/api"):
            continue
        methods = sorted(
            method
            for method in (getattr(route, "methods", set()) or set())
            if method not in {"HEAD", "OPTIONS"}
        )
        rotas.append(
            {
                "path": path,
                "methods": methods,
                "name": getattr(route, "name", None),
            }
        )
    return sorted(rotas, key=lambda route: route["path"])


@router.get("/mapa")
async def mapa_modulos(
    request: Request,
    cu: User = Depends(_gestores),
    db: AsyncSession = Depends(get_db),
):
    rotas_api = _coletar_rotas_api(request.app)
    try:
        result = await asyncio.wait_for(
            db.execute(
                select(ModuleHelp.module_key)
                .where(ModuleHelp.ativo.is_(True))
                .distinct()
            ),
            timeout=1.5,
        )
        helps_ativos: list[str] | None = [
            str(key) for key in result.scalars().all() if key
        ]
    except Exception:
        # Falha ao ler a ajuda não pode virar afirmação falsa de que todos os
        # módulos estão sem manual. O mapa continua funcional e declara o
        # estado documental como desconhecido.
        await db.rollback()
        helps_ativos = None

    mapa = gerar_mapa_modulos(rotas_api, helps_ativos)
    return {
        "resumo": resumir_mapa_modulos(mapa),
        "modulos": mapa,
        "rotas_api_detectadas": len(rotas_api),
        "modo": "somente_leitura",
        "documentacao_modo": (
            "persistida" if helps_ativos is not None else "indisponivel"
        ),
    }


@router.get("/integrations")
async def status_integracoes(
    cu: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Inventário seguro: configuração + Cofre + último estado operacional persistido."""
    try:
        credenciais = await credential_vault_service.estados_credenciais(db)
    except Exception:
        await db.rollback()
        credenciais = {}
    operacao = await coletar_estados_operacionais(db)
    return build_integration_status(get_settings(), credential_states=credenciais, operational_states=operacao)
