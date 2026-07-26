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

# ── Crypto ────────────────────────────────────────────────────────────────────
# bcrypt puro (passlib descontinuado e incompatível com bcrypt>=4.1)
bearer_scheme = HTTPBearer(auto_error=False)

# ── Hierarquia de perfis (nível numérico = poder) ─────────────────────────────
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
    """Gate compartilhado (fonte única): atos jurídicos exigem advogado+.

    Aceita User ORM ou objeto com .role (enum ou string). Levanta 403 quando o
    nível do papel é inferior a ROLE_LEVEL["advogado"]. Reusado pelos gates de
    kit documental, honorários, matriz de teses e orquestrador (defesa em
    profundidade — nunca enfraquecer)."""
    role = getattr(getattr(cu, "role", None), "value", None) or str(getattr(cu, "role", "") or "")
    if ROLE_LEVEL.get(role, 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(status_code=403, detail=detail)

# ── Permissões explícitas por perfil (SEM duplicação — bug v2 corrigido) ──────
ROLES_PERMISSOES: dict[str, list[str]] = {
    "superadmin": ["*"],
    "admin": [
        "usuarios", "modulos", "configuracoes", "auditoria",
        "clientes", "casos", "prazos", "tarefas", "documentos",
        "legal_docs", "honorarios", "ambiental", "ia", "dashboard",
        "relatorios", "notificacoes",
    ],
    # CORREÇÃO: "socio" tinha entrada duplicada com ["*"] — removida
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


# ── Hash de senha ─────────────────────────────────────────────────────────────
def verify_password(plain: str, hashed: str) -> bool:
    # bcrypt limita a 72 bytes — truncar é o comportamento padrão da lib
    try:
        return bcrypt.checkpw(plain.encode("utf-8", errors="replace")[:72], hashed.encode())
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt(rounds=12)).decode()


# ── JWT tokens ────────────────────────────────────────────────────────────────
def create_access_token(
    user_id: str,
    role: str,
    must_change_password: bool = False,
    two_factor_setup_required: bool = False,
    expires_minutes: int | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        timedelta(minutes=expires_minutes)
        if expires_minutes is not None
        else timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    )
    payload = {
        "sub": user_id,
        **({"pwd_change_required": True} if must_change_password else {}),
        **({"two_factor_setup_required": True} if two_factor_setup_required else {}),
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """
    Cria refresh token com JTI único (revogável).
    Retorna (token_jwt, jti) — jti deve ser salvo no banco.
    """
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


# ── Dependency: usuário autenticado atual ─────────────────────────────────────
from app.core.database import get_db   # import local para evitar circular

async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
):
    """
    Extrai e valida o JWT do header Authorization: Bearer <token>.
    Retorna o objeto User autenticado ou lança 401.
    """
    from app.models.user import User   # import local evita circular

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
    """
    Dependency factory HIERÁRQUICA: libera o acesso se o usuário tem um dos
    perfis listados OU nível hierárquico >= ao menor nível dos perfis listados.

    ATENÇÃO (SYS-009): o fallback por nível deixa papéis de nível SUPERIOR
    atravessarem gates LATERAIS. Ex.: um gate `require_roles(["financeiro"])`
    (nível 4) é atravessado por advogado (6)/admin (8), pois o nível deles é
    maior — mesmo sem pertencerem à área financeira. Use `require_roles` apenas
    quando a semântica desejada for REALMENTE "este nível ou acima" (gates
    verticais de senioridade). Para gates de ÁREA/competência lateral (financeiro,
    auditoria, etc.), use `require_roles_exact()` (allowlist estrita, sem
    fallback de nível).
    """
    async def checker(current_user=Depends(get_current_user)):
        if current_user.role not in allowed:
            user_level = ROLE_LEVEL.get(current_user.role, 0)
            min_level  = min(ROLE_LEVEL.get(r, 0) for r in allowed)
            if user_level < min_level:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Acesso negado. Perfis permitidos: {', '.join(allowed)}",
                )
        return current_user
    return checker


def require_roles_exact(*roles: str):
    """
    Dependency factory ESTRITA (allowlist): exige pertencimento EXATO ao conjunto
    de papéis, SEM fallback hierárquico de nível (SYS-009).

    Diferente de `require_roles`, um papel de nível superior NÃO atravessa o gate
    só por ter nível maior — precisa estar explicitamente listado. É a forma
    correta para gates LATERAIS de área/competência (ex.: financeiro, auditoria),
    onde "mais sênior" não implica "autorizado nesta área".

    Uso: `Depends(require_roles_exact("financeiro", "admin", "superadmin"))`.
    Liste TODOS os papéis que devem passar (inclua explicitamente os
    administrativos que precisam de acesso).
    """
    permitidos = frozenset(roles)

    async def checker(current_user=Depends(get_current_user)):
        role = getattr(getattr(current_user, "role", None), "value", None) \
            or str(getattr(current_user, "role", "") or "")
        if role not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado. Perfis permitidos: {', '.join(sorted(permitidos))}",
            )
        return current_user
    return checker


# Alias em português (padrão do repo: requer_advogado/exigir_*).
exigir_papeis_estritos = require_roles_exact


def require_admin(cu=Depends(get_current_user)):
    """Shortcut: exige admin ou superior."""
    if ROLE_LEVEL.get(cu.role, 0) < ROLE_LEVEL["admin"]:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return cu
