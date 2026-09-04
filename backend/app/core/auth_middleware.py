# ── app/core/auth_middleware.py ────────────────────────────────────────────────
# Middleware GLOBAL de autenticação JWT.
from __future__ import annotations

import logging
import posixpath
import re

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
    "/api/data-rooms/acesso/",
    "/api/rag/knowledge-base/",
)

_CALENDAR_FEED_PUBLICO_RE = re.compile(
    r"^/api/calendar/[^/]+/[0-9a-f]{32}\.ics$",
    flags=re.IGNORECASE,
)


def _api_path_interno(path: str) -> str:
    """Normaliza segmentos e converte o prefixo canônico /api/v1 em /api.

    A autenticação não pode depender da posição relativa do middleware de
    versionamento. O restante do path permanece intacto para não ampliar a
    superfície pública por correspondência textual parcial.
    """
    normalized = posixpath.normpath(path)
    # `posixpath.normpath` PRESERVA exatamente duas barras iniciais (regra POSIX:
    # "//" é reservado para interpretação definida pela implementação). Sem
    # colapsar, "//api/casos" continua "//api/casos", deixa de casar o
    # `startswith("/api/")` de `_is_publica` e a requisição seria liberada SEM
    # JWT — fail-open. Hoje o roteador do Starlette não casa esse path (404) e o
    # nginx colapsa barras antes do proxy, mas a autenticação não pode depender
    # de nenhuma das duas: qualquer normalização a jusante viraria bypass real.
    if normalized.startswith("//"):
        normalized = "/" + normalized.lstrip("/")
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


def _calendar_feed_assinado_publico(path: str) -> bool:
    """Libera apenas o feed ICS portador de token HMAC, nunca a gestão do feed.

    `/calendar/me/url` e `/calendar/me/rotate` dependem de JWT e também devem
    passar pelos gates globais de troca de senha, 2FA e isolamento do Portal.
    """
    return _CALENDAR_FEED_PUBLICO_RE.fullmatch(path) is not None


def _is_publica(path: str) -> bool:
    """Retorna True se a rota não exige JWT, após normalização segura."""
    path = _api_path_interno(path)
    if not path.startswith("/api/"):
        return True
    if _calendar_feed_assinado_publico(path):
        return True
    return any(_path_casa_prefixo_publico(path, p) for p in PREFIXOS_PUBLICOS)


def _totp_management_temporarily_disabled(path: str) -> bool:
    """Bloqueia alteração de TOTP enquanto a política global estiver desligada.

    O login deixa de exigir o segundo fator, mas os endpoints de setup, ativação
    e desativação não podem sobrescrever ou apagar o segredo preservado durante
    a janela temporária. A normalização cobre igualmente rotas `/api/v1`.
    """
    path = _api_path_interno(path)
    return not two_factor_enabled() and _path_casa_prefixo_publico(
        path, "/api/auth/totp"
    )


def _registrar_uso_de_rota(request, status_code: int) -> None:
    """Telemetria de uso das rotas candidatas à remoção (Onda 3 §4.5).

    Roda DEPOIS da resposta, fora do caminho crítico. Falha aqui jamais afeta a
    requisição (best-effort; ver services/route_usage.py).

    INTEGRIDADE DO CONTADOR (P2-1): só registra quando o roteamento REALMENTE
    casou uma rota (``request.scope["route"]``) e quando a resposta foi
    bem-sucedida (< 400). Sem isso, qualquer usuário autenticado forjaria uso:
    ``GET /api/tasks/%7Btask_id%7D`` cairia no fallback para o path concreto e
    um 404 contaria como chamada da rota-template; e um 403/405 numa rota
    monitorada faria uma tela morta parecer viva. Não há fallback para
    ``request.url.path`` — path concreto nunca é registrado.
    """
    try:
        if status_code >= 400:
            return
        rota = request.scope.get("route")
        template = getattr(rota, "path", None)
        if not template:
            return

        from app.services import route_usage

        route_usage.registrar(template, request.method, getattr(request.state, "role", None))
    except Exception:  # pragma: no cover
        pass


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

        if _totp_management_temporarily_disabled(path):
            return JSONResponse(
                status_code=409,
                content={
                    "detail": (
                        "A configuração do 2FA está temporariamente suspensa. "
                        "O autenticador já cadastrado foi preservado."
                    ),
                    "two_factor_temporarily_disabled": True,
                },
            )

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

        resposta = await call_next(request)
        _registrar_uso_de_rota(request, getattr(resposta, "status_code", 500))
        return resposta
