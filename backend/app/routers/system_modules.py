from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.config import get_settings
from app.core.security import require_admin, require_roles
from app.models.user import User
from app.services.integration_status import build_integration_status
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
async def mapa_modulos(request: Request, cu: User = Depends(_gestores)):
    rotas_api = _coletar_rotas_api(request.app)
    mapa = gerar_mapa_modulos(rotas_api, [])
    return {
        "resumo": resumir_mapa_modulos(mapa),
        "modulos": mapa,
        "rotas_api_detectadas": len(rotas_api),
        "modo": "somente_leitura",
    }


@router.get("/integrations")
async def status_integracoes(cu: User = Depends(require_admin)):
    """Inventário de configuração sem chaves, tokens, senhas ou valores do ambiente."""
    return build_integration_status(get_settings())
