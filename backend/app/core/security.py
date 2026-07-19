# ── app/core/security.py ─────────────────────────────────────────────────────
# JWT, hash de senha (bcrypt), controle de acesso por perfil (RBAC).
# CORREÇÃO v2: eliminada chave duplicada "socio" que causava escalação de privilégio.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Annotated
from uuid import uuid4

import jwt
from jwt.exceptions import InvalidTokenError as JWTError
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings

settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=False)

ROLE_LEVEL: dict[str, int] = {
    "superadmin":    9,
    "admin":         8,
    "socio":         7,
    "advogado":      6,
    "advogado_auxiliar": 5,
    "financeiro":    4,
    "estagiario":    3,
    "secretaria":    2,
    "cliente_externo": 1,
}


def requer_advogado(cu, detail: str = "Acesso restrito a advogados") -> None:
    """Gate compartilhado (fonte única): atos jurídicos exigem advogado+."""
    role = getattr(getattr(cu, "role", None), "value", None) or str(getattr(cu, "role", "") or "")
    if ROLE_LEVEL.get(role, 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(status_code=403, detail=detail)


ROLES_PERMISSOES: dict[str, list[str]] = {
    "superadmin": ["*"],
    "admin": [
        "usuarios", "modulos", "configuracoes", "auditoria",
        "clientes", "casos", "prazos", "tarefas", "documentos",
        "legal_docs", "honorarios", "ambiental", "ia", "dashboard",
        "relatorios", "notificacoes",
    ],
    "socio": [
        "clientes", "casos", "prazos", "tarefas", "documentos",
        "legal_docs", "honorarios", "ambiental", "ia", "dashboard",
        "relatorios", "notificacoes", "auditoria",
    ],
    "advogado": [
        "clientes", "casos", "prazos", "tarefas", "documentos",
        "legal_docs", "ambiental", "ia", "dashboard",
    ],
    "advogado_auxiliar": [
        "casos_proprios", "prazos_proprios", "tarefas_proprias",
        "documentos_caso", "ia",
    ],
    "financeiro": [
        "honorarios", "relatorios_financeiros", "clientes_basico",
    ],
    "estagiario": [
        "casos_leitura", "tarefas", "documentos", "prazos_leitura",
    ],
    "secretaria": [
        "clientes", "leads", "dashboard_atendimento",
    ],
    "cliente_externo": [
        "meu_caso", "meus_documentos",
    ],
}


def has_permission(role: str, permission: str) -> bool:
    perms = ROLES_PERMISSOES.get(role, [])
    return "*" in perms or permission in perms


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8", errors="replace")[:72], hashed.encode())
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt(rounds=12)).decode()


def create_access_token(
    user_id: str,
    role: str,
    must_change_password: bool = False,
    two_factor_setup_required: bool = False,
) -> str:
    """Emite access token com claims restritivos fail-closed.

    `two_factor_setup_required` cria uma sessão limitada exclusivamente ao fluxo
    de configuração do autenticador e logout. O middleware aplica o bloqueio.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        hours=settings.ACCESS_TOKEN_EXPIRE_HOURS
    )
    payload = {
        "sub": user_id,
        **({"pwd_change_required": True} if must_change_password else {}),
        **(
            {"two_factor_setup_required": True}
            if two_factor_setup_required
            else {}
        ),
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """Cria refresh token com JTI único e retorna (token, jti)."""
    jti = str(uuid4())
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": user_id,
        "jti": jti,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError:
        return None


from app.core.database import get_db


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
):
    """Extrai e valida o JWT e retorna o usuário ativo."""
    from app.models.user import User

    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        raise exc

    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise exc

    user_id: str = payload.get("sub")
    if not user_id:
        raise exc

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_active == True,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise exc

    return user


def require_roles(allowed: List[str]):
    """Dependency factory: exige papel listado ou nível hierárquico suficiente."""
    async def checker(current_user=Depends(get_current_user)):
        role = getattr(current_user.role, "value", current_user.role)
        if role not in allowed:
            user_level = ROLE_LEVEL.get(role, 0)
            min_level = min(ROLE_LEVEL.get(r, 0) for r in allowed)
            if user_level < min_level:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Acesso negado. Perfis permitidos: {', '.join(allowed)}",
                )
        return current_user
    return checker


def require_admin(cu=Depends(get_current_user)):
    """Shortcut: exige admin ou superior."""
    role = getattr(cu.role, "value", cu.role)
    if ROLE_LEVEL.get(role, 0) < ROLE_LEVEL["admin"]:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return cu
