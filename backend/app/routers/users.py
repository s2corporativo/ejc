# ── app/routers/users.py ─────────────────────────────────────────────────────
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import os
from uuid import uuid4

import aiofiles
import magic  # python-magic — validação por magic bytes (mesmo padrão de documents.py)
import pyotp
import qrcode
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func as sqlfunc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    ROLE_LEVEL,
    ROLES_PERMISSOES,
    decode_token,
    get_current_user,
    get_password_hash,
    require_admin,
)
from app.models.audit_log import criar_audit_log
from app.models.user import RefreshToken, User
from app.schemas.auth import UserCreate, UserResponse, UserUpdate
from app.services.security_service import obter_ip_real, validar_forca_senha
from app.schemas.common import MsgResponse

settings = get_settings()
router = APIRouter(prefix="/users", tags=["Usuários"])
REFRESH_COOKIE = "ejc_refresh"


def _role_value(role) -> str:
    return str(getattr(role, "value", role))


def _nivel(role) -> int:
    return ROLE_LEVEL.get(_role_value(role), 0)


def _permissoes(role) -> list[str]:
    return list(ROLES_PERMISSOES.get(_role_value(role), []))


def _refresh_jti_atual(request: Request) -> str | None:
    token = request.cookies.get(REFRESH_COOKIE)
    payload = decode_token(token) if token else None
    if not payload or payload.get("type") != "refresh":
        return None
    return payload.get("jti")


def _validar_atribuicao_role(cu: User, novo_role: str | None) -> None:
    """Impede atribuir perfil desconhecido ou superior ao perfil do operador."""
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
    """Impede gerenciar usuário de nível IGUAL ou superior ao do operador.

    P4 (anti-lockout / escalada horizontal): com `>` estrito, um admin (nível 8)
    podia desativar/rebaixar OUTRO admin de mesmo nível — trancando um par para
    fora. Com `>=`, só um perfil estritamente superior gerencia (superadmin gere
    admin; admins não gerem entre si). Auto-gestão é tratada à parte pelo chamador
    (o admin ainda edita seus próprios campos_self; não pode se autodesativar)."""
    if _nivel(alvo.role) >= _nivel(cu.role):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para gerenciar usuário de nível igual ou superior ao seu.",
        )


@router.get("/me", response_model=UserResponse)
async def meu_perfil(cu: User = Depends(get_current_user)):
    """Dados do usuário autenticado."""
    return cu


@router.get("/me/security")
async def minha_seguranca(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Estado seguro da conta; nunca retorna segredo TOTP ou refresh token."""
    agora = datetime.now(timezone.utc)
    sessoes_ativas = (
        await db.execute(
            select(sqlfunc.count(RefreshToken.id)).where(
                RefreshToken.user_id == cu.id,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > agora,
            )
        )
    ).scalar() or 0
    return {
        "permissions": _permissoes(cu.role),
        "totp_enabled": bool(cu.totp_enabled),
        "active_sessions": int(sessoes_ativas),
        "two_factor_available": True,
    }


@router.get("/me/sessions")
async def minhas_sessoes(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista sessões refresh ativas sem expor token, JTI, IP ou identificadores secretos."""
    agora = datetime.now(timezone.utc)
    atual = _refresh_jti_atual(request)
    rows = (
        await db.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == cu.id,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > agora,
            )
            .order_by(RefreshToken.created_at.desc())
        )
    ).scalars().all()
    return {
        "data": [
            {
                "id": row.id,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "current": bool(atual and row.jti == atual),
            }
            for row in rows
        ],
        "total": len(rows),
        "metadata_available": ["created_at", "expires_at", "current"],
    }


@router.post("/me/sessions/revoke-others")
async def revogar_outras_sessoes(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Revoga todas as sessões refresh, exceto a representada pelo cookie atual."""
    atual = _refresh_jti_atual(request)
    if not atual:
        raise HTTPException(
            status_code=400,
            detail="Sessão atual sem refresh válido. Faça login novamente.",
        )
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == cu.id,
            RefreshToken.revoked.is_(False),
            RefreshToken.jti != atual,
        )
        .values(revoked=True)
    )
    quantidade = int(result.rowcount or 0)
    await criar_audit_log(
        db,
        cu.id,
        _role_value(cu.role),
        "SESSOES_REVOGADAS",
        "users",
        cu.id,
        detalhes=f"outras_sessoes={quantidade}",
        ip=obter_ip_real(request),
    )
    await db.commit()
    return {"detail": "Outras sessões revogadas.", "revoked": quantidade}


@router.post("/me/sessions/{session_id}/revoke")
async def revogar_sessao(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Revoga uma sessão remota pertencente ao próprio usuário."""
    row = (
        await db.execute(
            select(RefreshToken).where(
                RefreshToken.id == session_id,
                RefreshToken.user_id == cu.id,
                RefreshToken.revoked.is_(False),
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    atual = _refresh_jti_atual(request)
    if atual and row.jti == atual:
        raise HTTPException(
            status_code=400,
            detail="Use a opção Sair para encerrar a sessão atual.",
        )
    row.revoked = True
    await criar_audit_log(
        db,
        cu.id,
        _role_value(cu.role),
        "SESSAO_REVOGADA",
        "users",
        cu.id,
        detalhes=f"session_id={row.id}",
        ip=obter_ip_real(request),
    )
    await db.commit()
    return {"detail": "Sessão revogada."}


@router.get("/me/totp-qr")
async def meu_qr_totp(cu: User = Depends(get_current_user)):
    """Retorna QR PNG apenas durante a configuração, nunca após a ativação."""
    if cu.totp_enabled:
        raise HTTPException(
            status_code=400,
            detail="2FA já está ativo; o segredo não pode ser reexibido.",
        )
    if not cu.totp_secret:
        raise HTTPException(
            status_code=400,
            detail="Inicie a configuração do 2FA antes de solicitar o QR Code.",
        )
    uri = pyotp.TOTP(cu.totp_secret).provisioning_uri(
        name=cu.email,
        issuer_name="EJC — De Paula Teixeira",
    )
    image = qrcode.make(uri)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Content-Disposition": "inline; filename=ejc-2fa.png",
        },
    )


@router.get("/")
async def listar(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_admin),
):
    q = select(User).where(User.deleted_at.is_(None)).order_by(User.full_name)
    total = (
        await db.execute(select(sqlfunc.count()).select_from(q.subquery()))
    ).scalar()
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return {
        "data": [UserResponse.model_validate(u) for u in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/", response_model=UserResponse, status_code=201)
async def criar(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_admin),
):
    exists = (
        await db.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="Email já cadastrado")

    _validar_atribuicao_role(cu, payload.role)
    # Política de senha forte também na criação de usuário (fecha o último ponto
    # de definição de senha; troca e reset já validam via validar_forca_senha).
    try:
        validar_forca_senha(payload.password, payload.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    user = User(
        id=str(uuid4()),
        email=payload.email.lower(),
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        phone=payload.phone,
        oab_number=payload.oab_number,
        must_change_password=True,
    )
    db.add(user)
    await criar_audit_log(db, cu.id, _role_value(cu.role), "CREATE", "users", user.id)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def atualizar(
    user_id: str,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    user = (
        await db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    mudancas = payload.model_dump(exclude_unset=True)
    eh_admin = _role_value(cu.role) in ("superadmin", "admin")

    campos_self = {
        "full_name",
        "phone",
        "oab_number",
        "djen_oab_numero",
        "djen_oab_uf",
    }
    if not eh_admin:
        if cu.id != user_id:
            raise HTTPException(status_code=403, detail="Sem permissão")
        extras = set(mudancas) - campos_self
        if extras:
            raise HTTPException(
                status_code=403,
                detail=f"Campos restritos a admin: {sorted(extras)}",
            )
    else:
        # P4: self-gestão do admin é permitida (campos próprios), mas gerenciar
        # OUTRO usuário exige nível estritamente superior (bloqueia lockout entre
        # pares). E ninguém se autodesativa via PATCH (paridade com o DELETE).
        if cu.id != user_id:
            _validar_alvo(cu, user)
        elif mudancas.get("is_active") is False:
            raise HTTPException(status_code=400, detail="Não pode desativar a si mesmo")
        if "role" in mudancas:
            _validar_atribuicao_role(cu, mudancas["role"])
            # M04 (homologação 2026-08-15): anti-lockout — o admin (e o
            # superadmin) não pode rebaixar o próprio perfil, pois isso pode
            # ser usado para burlar audit/autorização ou trancar a gestão.
            if cu.id == user_id and _nivel(mudancas["role"]) < _nivel(cu.role):
                raise HTTPException(
                    status_code=400,
                    detail="Não é permitido rebaixar o próprio perfil",)
        elif "is_active" in mudancas and mudancas.get("is_active") is True and cu.id == user_id:
            # auto-reativação não faz sentido e mascara manipulação
            raise HTTPException(status_code=400,
                                detail="Não é permitido ativar o próprio perfil")

    for key, value in mudancas.items():
        setattr(user, key, value)
    await criar_audit_log(
        db,
        cu.id,
        _role_value(cu.role),
        "UPDATE",
        "users",
        user_id,
    )
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
    user = (
        await db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    _validar_alvo(cu, user)
    user.deleted_at = datetime.now(timezone.utc)
    user.is_active = False
    await criar_audit_log(
        db,
        cu.id,
        _role_value(cu.role),
        "DELETE",
        "users",
        user_id,
    )
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
# ═════════════════════════════════════════════════════════════════════════════
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_MIME_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
AVATAR_EXT_MIME = {value: key for key, value in AVATAR_MIME_EXT.items()}


def _validar_avatar(conteudo: bytes, content_type: str | None) -> tuple[str, str]:
    if content_type not in AVATAR_MIME_EXT:
        raise HTTPException(
            status_code=415,
            detail="Formato não suportado. Envie JPEG, PNG ou WebP.",
        )
    if len(conteudo) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Avatar excede 2MB")
    mime_real = magic.from_buffer(conteudo[:2048], mime=True)
    if mime_real not in AVATAR_MIME_EXT:
        raise HTTPException(
            status_code=415,
            detail=f"Conteúdo do arquivo ({mime_real}) não é JPEG/PNG/WebP.",
        )
    return mime_real, AVATAR_MIME_EXT[mime_real]


def _avatar_dir() -> str:
    directory = os.path.join(settings.UPLOAD_DIR, "avatars")
    os.makedirs(directory, exist_ok=True)
    return directory


def _apagar_avatares(user_id: str, exceto_ext: str | None = None) -> None:
    directory = _avatar_dir()
    for extension in AVATAR_MIME_EXT.values():
        if extension == exceto_ext:
            continue
        try:
            os.remove(os.path.join(directory, f"{user_id}{extension}"))
        except FileNotFoundError:
            pass


@router.post("/me/avatar", response_model=UserResponse)
async def enviar_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    conteudo = await file.read()
    _, extension = _validar_avatar(conteudo, file.content_type)

    destino = os.path.join(_avatar_dir(), f"{cu.id}{extension}")
    async with aiofiles.open(destino, "wb") as file_handle:
        await file_handle.write(conteudo)
    _apagar_avatares(cu.id, exceto_ext=extension)

    cu.avatar_url = f"/users/{cu.id}/avatar"
    await criar_audit_log(
        db,
        cu.id,
        _role_value(cu.role),
        "UPDATE",
        "users",
        cu.id,
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
    _apagar_avatares(cu.id)
    cu.avatar_url = None
    await criar_audit_log(
        db,
        cu.id,
        _role_value(cu.role),
        "UPDATE",
        "users",
        cu.id,
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
    if user_id == "me":
        user_id = cu.id
    # Avatar próprio sempre acessível (inclui portal); avatar de OUTROS só para
    # staff (estagiário+). cliente_externo não enumera avatares alheios. 404
    # (não 403) para não confirmar existência do usuário.
    if user_id != cu.id and _nivel(cu.role) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(status_code=404, detail="Usuário sem avatar")
    user = (
        await db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not user or not user.avatar_url:
        raise HTTPException(status_code=404, detail="Usuário sem avatar")

    directory = _avatar_dir()
    for extension, mime in AVATAR_EXT_MIME.items():
        caminho = os.path.join(directory, f"{user_id}{extension}")
        if os.path.exists(caminho):
            return FileResponse(caminho, media_type=mime)
    raise HTTPException(status_code=404, detail="Arquivo de avatar não encontrado")
