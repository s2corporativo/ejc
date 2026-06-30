# ── app/core/auth_middleware.py ───────────────────────────────────────────────
# Middleware GLOBAL de autenticação JWT.
# CORREÇÃO P0-1 DO EJC v2: este middleware estava escrito mas NUNCA registrado
# no main.py. Em v3, ele É registrado em main.py desde o primeiro deploy.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import logging
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import jwt
from jwt.exceptions import InvalidTokenError as JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Prefixos públicos — NÃO requerem JWT
# Manter lista enxuta: apenas o que realmente precisa ser público
PREFIXOS_PUBLICOS = (
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",     # logout aceita token expirado p/ revogar refresh
    "/api/auth/recuperar-senha",
    "/api/auth/redefinir-senha",
    "/api/health",
    "/api/docs",
    "/api/openapi.json",
    "/api/webhooks/",       # Z-API inbound (valida Client-Token internamente)
    "/api/calendar/",       # feed ICS (HMAC na URL)
)


def _is_publica(path: str) -> bool:
    """Retorna True se a rota não exige JWT."""
    if not path.startswith("/api/"):
        return True  # arquivos estáticos, etc.
    return any(path.startswith(p) for p in PREFIXOS_PUBLICOS)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware global: valida JWT em todas as rotas /api/v1/* protegidas.
    Injeta user_id e role no request.state para uso nas rotas.
    NÃO substitui os Depends(get_current_user) por rota — são complementares.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_publica(request.url.path):
            return await call_next(request)

        # Extrai token do header Authorization: Bearer <token>
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
            # Injeta no state para logging/auditoria
            request.state.user_id = payload.get("sub")
            request.state.role    = payload.get("role", "")
            path = request.url.path
        except JWTError as e:
            logger.warning(f"JWT inválido em {request.url.path}: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Token inválido ou expirado"},
            )

        # ── Troca de senha OBRIGATÓRIA: bloqueia tudo até trocar ─────────
        if payload.get("pwd_change_required"):   # must_change_password (claim no access token)
            liberados = ("/api/auth/alterar-senha", "/api/auth/logout")
            if not any(path.startswith(p) for p in liberados):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Troca de senha obrigatória. "
                             "Use /api/auth/alterar-senha.",
                             "must_change_password": True},
                )

        # ── Portal do Cliente: cliente_externo SÓ acessa /api/portal ─────
        # Isolamento LGPD: dados internos do escritório ficam inacessíveis
        # mesmo com token válido. Guarda central — vale p/ TODAS as rotas.
        if request.state.role == "cliente_externo":
            permitidos = ("/api/portal/", "/api/auth", "/api/health",
                          "/api/notifications", "/api/signatures")
            if not any(path.startswith(p) for p in permitidos):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Acesso restrito ao Portal do Cliente"},
                )

        return await call_next(request)
