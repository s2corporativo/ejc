# ── app/core/auth_middleware.py ───────────────────────────────────────────────
# Middleware GLOBAL de autenticação JWT.
from __future__ import annotations

import logging
import posixpath

from fastapi import Request, Response
from fastapi.responses import JSONResponse
import jwt
from jwt.exceptions import InvalidTokenError as JWTError
from sqlalchemy import select
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


def _api_path_interno(path: str) -> str:
    """Normaliza segmentos e converte o prefixo canônico /api/v1 em /api."""
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


def _papeis_2fa_obrigatorio() -> set[str]:
    """Política efetiva de 2FA.

    Em produção, uma configuração vazia não pode desligar silenciosamente a
    proteção dos perfis de maior privilégio. Para desativação deliberada, deve-se
    informar explicitamente um CSV sem esses papéis em ambiente não produtivo.
    """
    configured = set(settings.require_2fa_roles_list)
    if configured:
        return configured
    if settings.APP_ENV == "production":
        return {"superadmin", "admin", "socio"}
    return set()


async def _precisa_configurar_2fa(payload: dict) -> bool:
    """Consulta o estado real do usuário e aplica a política por papel.

    A checagem em banco impede que tokens antigos, refresh ou clientes que
    ignorem a flag do login contornem o enforcement. Falha de banco é fail-closed
    para papéis obrigados, preservando apenas as rotas de configuração/logout.
    """
    role = str(payload.get("role") or "").strip().lower()
    if role not in _papeis_2fa_obrigatorio():
        return False
    user_id = payload.get("sub")
    if not user_id:
        return True
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.user import User

        async with AsyncSessionLocal() as db:
            enabled = await db.scalar(
                select(User.totp_enabled).where(
                    User.id == user_id,
                    User.is_active == True,
                    User.deleted_at.is_(None),
                )
            )
        return enabled is not True
    except Exception:
        logger.exception("Falha ao validar enforcement de 2FA para user=%s", user_id)
        return True


class AuthMiddleware(BaseHTTPMiddleware):
    """Valida JWT e aplica gates de senha, 2FA e isolamento do portal."""

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

        # A troca de senha tem precedência sobre a configuração de 2FA.
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

        # Enforcement duro de 2FA, baseado no banco e não apenas em flag visual.
        if await _precisa_configurar_2fa(payload):
            liberados_2fa = (
                "/api/auth/totp/setup",
                "/api/auth/totp/verificar",
                "/api/auth/logout",
            )
            if not any(_path_casa_prefixo_publico(path, p) for p in liberados_2fa):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            "Seu perfil exige autenticação de dois fatores. "
                            "Configure e confirme o autenticador antes de continuar."
                        ),
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
