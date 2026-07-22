# ── app/core/auth_middleware.py ───────────────────────────────────────────────
# Middleware GLOBAL de autenticação JWT.
from __future__ import annotations

import logging
import posixpath

from fastapi import Request, Response
from fastapi.responses import JSONResponse
import jwt
from jwt.exceptions import InvalidTokenError as JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.two_factor_policy import two_factor_enabled

logger = logging.getLogger(__name__)
settings = get_settings()

# Prefixos públicos no contrato interno /api. O helper `_api_path_interno`
# normaliza /api/v1 antes de consultar esta lista.
PREFIXOS_PUBLICOS = (
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/api/auth/recuperar-senha",
    "/api/auth/redefinir-senha",
    "/api/health",
    "/api/docs",
    "/api/openapi.json",
    "/api/webhooks/",
    "/api/calendar/",
    "/api/data-rooms/acesso/",
    "/api/rag/knowledge-base/",
)


def _api_path_interno(path: str) -> str:
    """Normaliza segmentos e converte o prefixo canônico /api/v1 em /api.

    A autenticação não pode depender da posição relativa do middleware de
    versionamento. O restante do path permanece intacto para não ampliar a
    superfície pública por correspondência textual parcial.
    """
    normalized = posixpath.normpath(path)
    if normalized == "/api/v1":
        return "/api"
    if normalized.startswith("/api/v1/"):
        return f"/api{normalized[len('/api/v1') :]}"
    return normalized


def _path_casa_prefixo_publico(path: str, prefixo: str) -> bool:
    """Casa rota exata ou subárvore deliberada sem falso prefixo textual."""
    if prefixo.endswith("/"):
        return path.startswith(prefixo)
    return path == prefixo or path.startswith(prefixo + "/")


def _is_publica(path: str) -> bool:
    """Retorna True se a rota não exige JWT, após normalização segura."""
    path = _api_path_interno(path)
    if not path.startswith("/api/"):
        return True
    return any(_path_casa_prefixo_publico(path, p) for p in PREFIXOS_PUBLICOS)


class AuthMiddleware(BaseHTTPMiddleware):
    """Valida JWT globalmente e aplica isolamento adicional do portal."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = _api_path_interno(request.url.path)
        if _is_publica(path):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Token de autenticação não fornecido"},
            )

        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
            )
            if payload.get("type") != "access":
                raise JWTError("Tipo de token inválido")
            request.state.user_id = payload.get("sub")
            request.state.role = payload.get("role", "")
        except JWTError as exc:
            logger.warning("JWT inválido em %s: %s", request.url.path, exc)
            return JSONResponse(
                status_code=401,
                content={"detail": "Token inválido ou expirado"},
            )

        if payload.get("pwd_change_required"):
            liberados = ("/api/auth/alterar-senha", "/api/auth/logout")
            if not any(_path_casa_prefixo_publico(path, p) for p in liberados):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Troca de senha obrigatória. Use /api/auth/alterar-senha.",
                        "must_change_password": True,
                    },
                )

        # Tokens emitidos antes da desativação podem conter o claim abaixo. A
        # política global tem precedência, evitando que sessões antigas permaneçam
        # presas na tela de setup enquanto o 2FA estiver temporariamente desligado.
        if (
            two_factor_enabled()
            and payload.get("two_factor_setup_required")
            and not payload.get("pwd_change_required")
        ):
            liberados_2fa = (
                "/api/auth/totp/setup",
                "/api/auth/totp/verificar",
                "/api/auth/logout",
            )
            if not any(
                _path_casa_prefixo_publico(path, prefixo)
                for prefixo in liberados_2fa
            ):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Configure a autenticação de dois fatores para continuar.",
                        "precisa_configurar_2fa": True,
                    },
                )

        if request.state.role == "cliente_externo":
            permitidos = (
                "/api/portal/",
                "/api/auth/",
                "/api/health",
                "/api/notifications",
                "/api/signatures",
                "/api/users/me",
            )
            if not any(_path_casa_prefixo_publico(path, p) for p in permitidos):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Acesso restrito ao Portal do Cliente"},
                )

        return await call_next(request)
