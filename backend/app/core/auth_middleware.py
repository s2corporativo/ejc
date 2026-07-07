# ── app/core/auth_middleware.py ───────────────────────────────────────────────
from __future__ import annotations
import logging
import posixpath
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import jwt
from jwt.exceptions import InvalidTokenError as JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

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


def _path_casa_prefixo_publico(path: str, prefixo: str) -> bool:
    if prefixo.endswith("/"):
        return path.startswith(prefixo)
    return path == prefixo or path.startswith(prefixo + "/")


def _is_publica(path: str) -> bool:
    path = posixpath.normpath(path)
    if not path.startswith("/api/"):
        return True
    return any(_path_casa_prefixo_publico(path, p) for p in PREFIXOS_PUBLICOS)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_publica(request.url.path):
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
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            if payload.get("type") != "access":
                raise JWTError("Tipo de token inválido")
            request.state.user_id = payload.get("sub")
            request.state.role = payload.get("role", "")
            path = request.url.path
        except JWTError as e:
            logger.warning(f"JWT inválido em {request.url.path}: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Token inválido ou expirado"},
            )

        if payload.get("pwd_change_required"):
            liberados = ("/api/auth/alterar-senha", "/api/auth/logout")
            if not any(path.startswith(p) for p in liberados):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Troca de senha obrigatória. Use /api/auth/alterar-senha.",
                        "must_change_password": True,
                    },
                )

        if request.state.role == "cliente_externo":
            permitidos = (
                "/api/portal/",
                "/api/auth",
                "/api/health",
                "/api/notifications",
                "/api/signatures",
            )
            if not any(path.startswith(p) for p in permitidos):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Acesso restrito ao Portal do Cliente"},
                )

        return await call_next(request)
