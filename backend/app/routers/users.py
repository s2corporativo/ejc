# ── app/routers/users.py ─────────────────────────────────────────────────────
from __future__ import annotations
import os
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

import aiofiles
import magic  # python-magic — validação por magic bytes (mesmo padrão de documents.py)
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import get_current_user, require_admin, get_password_hash, ROLE_LEVEL
from app.models.user import User
from app.models.audit_log import criar_audit_log
from app.schemas.auth import UserCreate, UserUpdate, UserResponse
from app.schemas.common import MsgResponse

settings = get_settings()
router = APIRouter(prefix="/users", tags=["Usuários"])


def _nivel(role) -> int:
    return ROLE_LEVEL.get(getattr(role, "value", role), 0)


def _validar_atribuicao_role(cu: User, novo_role: str | None) -> None:
    """Anti-escalonamento: o perfil deve ser CONHECIDO e de nível ≤ ao do próprio
    `cu`. Impede que um admin (8) crie/promova alguém a superadmin (9, wildcard)."""
    if novo_role is None:
        return
    if novo_role not in ROLE_LEVEL:
        raise HTTPException(status_code=422, detail=f"Perfil inválido: {novo_role}")
    if _nivel(novo_role) > _nivel(cu.role):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para conceder perfil de nível superior ao seu.",
        )


def _validar_alvo(cu: User, alvo: User) -> None:
    """Impede gerenciar (alterar/desativar) um usuário de nível SUPERIOR ao próprio
    (ex.: um admin desativar/rebaixar um superadmin)."""
    if _nivel(alvo.role) > _nivel(cu.role):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para gerenciar usuário de nível superior ao seu.",
        )


@router.get("/me", response_model=UserResponse)
async def meu_perfil(cu: User = Depends(get_current_user)):
    """Dados do usuário autenticado (inclui avatar_url)."""
    return cu


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_admin),
):
    q = select(User).where(User.deleted_at.is_(None)).order_by(User.full_name)
    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [UserResponse.model_validate(u) for u in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/", response_model=UserResponse, status_code=201)
async def criar(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_admin),
):
    exists = (await db.execute(
        select(User).where(User.email == payload.email.lower())
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="Email já cadastrado")

    _validar_atribuicao_role(cu, payload.role)
    user = User(
        id=str(uuid4()), email=payload.email.lower(),
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name, role=payload.role,
        phone=payload.phone, oab_number=payload.oab_number,
    )
    db.add(user)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "users", user.id)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def atualizar(
    user_id: str, payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    user = (await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    mudancas = payload.model_dump(exclude_unset=True)
    eh_admin = cu.role.value in ("superadmin", "admin")

    # Não-admin: só edita a PRÓPRIA conta e apenas campos pessoais seguros
    CAMPOS_SELF = {"full_name", "phone", "oab_number",
                   "djen_oab_numero", "djen_oab_uf"}
    if not eh_admin:
        if cu.id != user_id:
            raise HTTPException(status_code=403, detail="Sem permissão")
        extras = set(mudancas) - CAMPOS_SELF
        if extras:
            raise HTTPException(status_code=403,
                                detail=f"Campos restritos a admin: {sorted(extras)}")
    else:
        # Admin: não pode gerenciar alguém de nível superior nem conceder um
        # perfil acima do próprio (anti-escalonamento vertical → superadmin).
        _validar_alvo(cu, user)
        if "role" in mudancas:
            _validar_atribuicao_role(cu, mudancas["role"])

    for k, v in mudancas.items():
        setattr(user, k, v)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "users", user_id)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=MsgResponse)
async def desativar(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_admin),
):
    """Soft delete — nunca DELETE físico."""
    if user_id == cu.id:
        raise HTTPException(status_code=400, detail="Não pode desativar a si mesmo")
    user = (await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    _validar_alvo(cu, user)  # admin não desativa superadmin
    user.deleted_at = datetime.now(timezone.utc)
    user.is_active = False
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "users", user_id)
    await db.commit()
    return MsgResponse(detail="Usuário desativado")


# ═══ URL do calendário ICS pessoal (token HMAC) ═══
from app.routers.calendar_feed import gerar_token_calendario
from app.core.config import get_settings as _gset


@router.get("/me/calendar-url")
async def minha_url_calendario(cu: User = Depends(get_current_user)):
    s = _gset()
    base = s.FRONTEND_URL.rstrip("/")
    token = gerar_token_calendario(cu.id)
    return {"url": f"{base}/api/calendar/{cu.id}/{token}.ics"}


# ═════════════════════════════════════════════════════════════════════════════
# FOTO DE PERFIL (avatar)
# Uploads não são servidos por StaticFiles em main.py — o padrão do projeto é
# endpoint autenticado com FileResponse (como GET /documents/{id}/download).
# Por isso avatar_url guarda o PATH da API (/users/{id}/avatar) e o arquivo é
# servido por rota autenticada (qualquer usuário logado; avatar é interno).
# ═════════════════════════════════════════════════════════════════════════════
AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
# MIME aceito → extensão canônica (extensão SEMPRE derivada do MIME validado
# por magic bytes, nunca do nome do arquivo enviado pelo cliente).
AVATAR_MIME_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png":  ".png",
    "image/webp": ".webp",
}
AVATAR_EXT_MIME = {v: k for k, v in AVATAR_MIME_EXT.items()}


def _validar_avatar(conteudo: bytes, content_type: str | None) -> tuple[str, str]:
    """
    Valida tamanho, content-type declarado e magic bytes do avatar.
    Retorna (mime_real, ext). Levanta 413/415 em caso de violação.
    """
    if content_type not in AVATAR_MIME_EXT:
        raise HTTPException(
            status_code=415,
            detail="Formato não suportado. Envie JPEG, PNG ou WebP.",
        )
    if len(conteudo) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Avatar excede 2MB")
    # Server-side: não confiar no content_type do cliente (padrão documents.py)
    mime_real = magic.from_buffer(conteudo[:2048], mime=True)
    if mime_real not in AVATAR_MIME_EXT:
        raise HTTPException(
            status_code=415,
            detail=f"Conteúdo do arquivo ({mime_real}) não é JPEG/PNG/WebP.",
        )
    return mime_real, AVATAR_MIME_EXT[mime_real]


def _avatar_dir() -> str:
    d = os.path.join(settings.UPLOAD_DIR, "avatars")
    os.makedirs(d, exist_ok=True)
    return d


def _apagar_avatares(user_id: str, exceto_ext: str | None = None) -> None:
    """Remove arquivos de avatar do usuário (tolerante a arquivo ausente)."""
    d = _avatar_dir()
    for e in AVATAR_MIME_EXT.values():
        if e == exceto_ext:
            continue
        try:
            os.remove(os.path.join(d, f"{user_id}{e}"))
        except FileNotFoundError:
            pass


@router.post("/me/avatar", response_model=UserResponse)
async def enviar_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Troca a foto de perfil do PRÓPRIO usuário (sobrescreve a anterior)."""
    conteudo = await file.read()
    _, ext = _validar_avatar(conteudo, file.content_type)

    destino = os.path.join(_avatar_dir(), f"{cu.id}{ext}")
    async with aiofiles.open(destino, "wb") as f:
        await f.write(conteudo)
    # Avatar antigo com outra extensão não pode ficar órfão no disco
    _apagar_avatares(cu.id, exceto_ext=ext)

    cu.avatar_url = f"/users/{cu.id}/avatar"
    await criar_audit_log(
        db, cu.id, cu.role.value, "UPDATE", "users", cu.id,
        detalhes="avatar atualizado",
    )
    await db.commit()
    await db.refresh(cu)
    return cu


@router.delete("/me/avatar", response_model=MsgResponse)
async def remover_avatar(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Remove a foto de perfil do PRÓPRIO usuário (tolerante a arquivo ausente)."""
    _apagar_avatares(cu.id)
    cu.avatar_url = None
    await criar_audit_log(
        db, cu.id, cu.role.value, "UPDATE", "users", cu.id,
        detalhes="avatar removido",
    )
    await db.commit()
    return MsgResponse(detail="Avatar removido")


@router.get("/{user_id}/avatar")
async def obter_avatar(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Serve a foto de perfil. Exige autenticação, mas NÃO ownership: avatar é
    conteúdo interno do sistema (exibido em listas, comentários, kanban etc.).
    Aceita "me" como alias do próprio usuário.
    """
    if user_id == "me":
        user_id = cu.id
    user = (await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not user or not user.avatar_url:
        raise HTTPException(status_code=404, detail="Usuário sem avatar")

    d = _avatar_dir()
    for ext, mime in AVATAR_EXT_MIME.items():
        caminho = os.path.join(d, f"{user_id}{ext}")
        if os.path.exists(caminho):
            return FileResponse(caminho, media_type=mime)
    raise HTTPException(status_code=404, detail="Arquivo de avatar não encontrado")
