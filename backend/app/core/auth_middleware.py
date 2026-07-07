# ── app/core/auth_middleware.py ───────────────────────────────────────────────
# Middleware GLOBAL de autenticação JWT.
# CORREÇÃO P0-1 DO EJC v2: este middleware estava escrito mas NUNCA registrado
# no main.py. Em v3, ele É registrado em main.py desde o primeiro deploy.
# ─────────────────────────────────────────────────────────────────────────────
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
    # P1-1: /api/victory_vault/ REMOVIDO da lista pública — expunha as teses
    # vitoriosas do escritório sem login. Agora exige JWT (Depends no router).
    "/api/webhooks/",       # Z-API inbound (valida Client-Token internamente)
    "/api/calendar/",       # feed ICS (HMAC na URL)
    # Data Room — acesso externo por LINK com token (48 bytes urlsafe) na URL:
    # o token É a credencial (valida expiração + max_acessos + log). Sem isto o
    # middleware bloqueava o cliente externo (sem JWT) com 401 e o
    # compartilhamento externo não funcionava. Só o subpath /acesso/ é público;
    # a gestão do Data Room (/api/data-rooms/...) segue exigindo JWT.
    "/api/data-rooms/acesso/",
    # API pública de abastecimento da base de conhecimento (Fase 2 IA/RAG):
    # NÃO usa JWT — exige API key de serviço (X-API-Key) validada pelo
    # require_api_key no router (401/403 lá; nada fica realmente aberto).
    "/api/rag/knowledge-base/",
)


def _path_casa_prefixo_publico(path: str, prefixo: str) -> bool:
    """Casa uma rota pública sem liberar prefixos textuais falsos.

    Prefixos terminados em "/" continuam funcionando como subárvore pública
    deliberada. Rotas sem "/" final aceitam somente a rota exata ou subrota
    real separada por barra. Ex.: "/api/health/ready" é público, mas
    "/api/auth/login-extra" não herda a liberação de "/api/auth/login".
    """
    if prefixo.endswith("/"):
        return path.startswith(prefixo)
    return path == prefixo or path.startswith(prefixo + "/")


def _is_publica(path: str) -> bool:
    """Retorna True se a rota não exige JWT.

    Auditoria B-1: normaliza o path (posixpath.normpath) ANTES do startswith —
    sem isso, "/api/rag/knowledge-base/../qualquer-coisa" casaria um prefixo
    público via segmentos "..", pulando o middleware para uma rota protegida.

    Auditoria P0: evita falso positivo por prefixo textual parcial. Ex.:
    "/api/auth/login-extra" não pode ser tratado como público.
    """
    path = posixpath.normpath(path)
    if not path.startswith("/api/"):
        return True  # arquivos estáticos, etc.
    return any(_path_casa_prefixo_publico(path, p) for p in PREFIXOS_PUBLICOS)


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
