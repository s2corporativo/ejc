from __future__ import annotations

from fastapi import HTTPException

from app.core.config import get_settings


def _require(enabled: bool, env_name: str, label: str) -> None:
    if enabled:
        return
    raise HTTPException(
        status_code=503,
        detail=f"{label} temporariamente desabilitado por configuração ({env_name}=false).",
    )


def require_entrada_unica_enabled() -> None:
    settings = get_settings()
    _require(settings.ENTRADA_UNICA_ENABLED, "ENTRADA_UNICA_ENABLED", "Entrada Única")


def require_financeiro_enabled() -> None:
    settings = get_settings()
    _require(settings.FINANCEIRO_ENABLED, "FINANCEIRO_ENABLED", "Financeiro")
