# ── app/routers/auth.py ───────────────────────────────────────────────────────
# Autenticação: login (2FA, brute-force, must_change, device_alert),
# refresh com rotação, logout, troca de senha, reset por e-mail.
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pyotp

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token, decode_token,
)
from app.models.user import User, RefreshToken
from app.models.audit_log import criar_audit_log
from app.services.security_service import (
    esta_bloqueado, registrar_falha, limpar_falhas, obter_ip_real,
    verificar_novo_dispositivo,
    solicitar_reset, confirmar_reset,
)

router  = APIRouter(prefix="/auth", tags=["Autenticação"])
settings = get_settings()


# ─── Schemas ──────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class AlterarSenhaRequest(BaseModel):
    senha_atual: str
    nova_senha: str = Field(min_length=8)


class ResetSolicitarRequest(BaseModel):
    email: EmailStr


class ResetConfirmarRequest(BaseModel):
    token: str
    nova_senha: str = Field(min_length=8)


class TOTPVerificarRequest(BaseModel):
    codigo: str = Field(min_length=6, max_length=6)

class TOTPDesativarRequest(BaseModel):
    codigo: str = Field(min_length=6, max_length=6)


# ─── Login ────────────────────────────────────────────────────────────────────
@router.post("/login")
@limiter.limit("10/minute")
async def login(
    req: LoginRequest, request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = obter_ip_real(request)
    chave_bf = f"ip:{ip}"        # bloqueia o IP
    chave_em = f"em:{req.email.lower()}"  # bloqueia o e-mail

    # ── 1. Anti-brute-force ──────────────────────────────────────────
    bloq_ip, seg_ip = esta_bloqueado(chave_bf)
    bloq_em, seg_em = esta_bloqueado(chave_em)
    if bloq_ip or bloq_em:
        restante = max(seg_ip, seg_em)
        raise HTTPException(
            status_code=429,
            detail=f"Muitas tentativas. Tente novamente em {restante//60+1} min.",
            headers={"Retry-After": str(restante)},
        )

    # ── 2. Credenciais ───────────────────────────────────────────────
    user = (await db.execute(
        select(User).where(
            User.email == req.email.lower(),
            User.is_active == True,
            User.deleted_at.is_(None),
        )
    )).scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        registrar_falha(chave_bf)
        registrar_falha(chave_em)
        await criar_audit_log(
            db, None, None, "LOGIN_FALHA", "users",
            detalhes=f"Tentativa: {req.email[:50]}",
            ip=ip,
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")

    # ── 3. TOTP (se habilitado) ──────────────────────────────────────
    if user.totp_enabled:
        if not req.totp_code:
            raise HTTPException(status_code=401, detail="TOTP obrigatório. Informe o código do autenticador.")
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(req.totp_code, valid_window=1):
            registrar_falha(chave_bf)
            registrar_falha(chave_em)
            await criar_audit_log(db, user.id, user.role.value, "LOGIN_TOTP_FALHA", "users", user.id, ip=ip)
            await db.commit()
            raise HTTPException(status_code=401, detail="Código TOTP inválido ou expirado")

    # ── 4. Login OK ──────────────────────────────────────────────────
    limpar_falhas(chave_bf)
    limpar_falhas(chave_em)

    access = create_access_token(user.id, user.role.value,
                                 must_change_password=user.must_change_password)
    refresh_tok, jti = create_refresh_token(user.id)

    db.add(RefreshToken(
        id=str(uuid4()), user_id=user.id, jti=jti,
        expires_at=datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    user.last_login_at = datetime.now(timezone.utc)

    await criar_audit_log(db, user.id, user.role.value, "LOGIN", "users",
                          user.id, ip=ip)

    # Alerta de novo dispositivo (assíncrono — não bloqueia resposta)
    ua = request.headers.get("user-agent", "")
    await verificar_novo_dispositivo(db, user, ip, ua)

    await db.commit()

    resp = {
        "access_token": access, "refresh_token": refresh_tok,
        "token_type": "bearer",
        "user_id": user.id, "full_name": user.full_name, "role": user.role.value,
    }
    # ── 5. Sinalizar troca obrigatória de senha ──────────────────────
    if user.must_change_password:
        resp["must_change_password"] = True
        resp["detail"] = "Troca de senha obrigatória antes de continuar."
    return resp


# ─── Refresh (rotação de token) ───────────────────────────────────────────────
@router.post("/refresh")
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token inválido")

    jti = payload.get("jti")
    record = (await db.execute(
        select(RefreshToken).where(
            RefreshToken.jti == jti,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )).scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=401, detail="Token revogado ou expirado")

    # Rotação: revogar o atual, emitir novo par
    record.revoked = True
    user_id = payload.get("sub")

    user = (await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário inativo")

    new_access = create_access_token(user.id, user.role.value)
    new_refresh, new_jti = create_refresh_token(user.id)

    db.add(RefreshToken(
        id=str(uuid4()), user_id=user.id, jti=new_jti,
        expires_at=datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.commit()
    return {"access_token": new_access, "refresh_token": new_refresh,
            "token_type": "bearer"}


# ─── Logout ───────────────────────────────────────────────────────────────────
@router.post("/logout")
async def logout(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if payload:
        jti = payload.get("jti")
        if jti:
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.jti == jti)
                .values(revoked=True)
            )
            await db.commit()
    return {"detail": "Logout realizado"}


# ─── Alterar senha (autenticado) ──────────────────────────────────────────────
@router.post("/alterar-senha")
async def alterar_senha(
    req: AlterarSenhaRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import get_current_user
    # Recria o fluxo manualmente para aceitar token must_change
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    token = auth.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token inválido")

    user = (await db.execute(
        select(User).where(User.id == payload.get("sub"), User.is_active == True)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")

    if not verify_password(req.senha_atual, user.hashed_password):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")

    user.hashed_password      = get_password_hash(req.nova_senha)
    user.must_change_password = False

    # Revogar TODAS as outras sessões (segurança pós-troca)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked == False)
        .values(revoked=True)
    )
    await criar_audit_log(
        db, user.id, user.role.value, "TROCA_SENHA", "users", user.id,
        ip=obter_ip_real(request),
    )
    await db.commit()
    return {"detail": "Senha alterada. Faça login novamente."}


# ─── Recuperação de senha (público) ──────────────────────────────────────────
@router.post("/recuperar-senha")
@limiter.limit("3/hour")
async def recuperar_senha(
    req: ResetSolicitarRequest, request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = obter_ip_real(request)
    await solicitar_reset(db, req.email, ip)
    return {"detail": "Se o e-mail existir, enviaremos as instruções em breve."}


@router.post("/redefinir-senha")
async def redefinir_senha(
    req: ResetConfirmarRequest,
    db: AsyncSession = Depends(get_db),
):
    ok = await confirmar_reset(db, req.token, req.nova_senha)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Link inválido ou expirado. Solicite um novo.",
        )
    return {"detail": "Senha redefinida com sucesso. Faça login."}


# ─── TOTP: Setup ──────────────────────────────────────────────────────────────
@router.post("/totp/setup")
async def totp_setup(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Gera segredo TOTP e URI para QR code. NÃO ativa ainda — requer /totp/verificar."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    payload = decode_token(auth.split(" ", 1)[1])
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token inválido")
    user = (await db.execute(
        select(User).where(User.id == payload.get("sub"), User.is_active == True)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="TOTP já está ativo. Desative antes de reconfigurar.")
    secret = pyotp.random_base32()
    user.totp_secret = secret
    await db.commit()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name="EJC — De Paula Teixeira")
    return {"secret": secret, "uri": uri, "aviso": "Use /totp/verificar com o primeiro código para ativar."}


@router.post("/totp/verificar")
async def totp_verificar(
    req: TOTPVerificarRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Ativa o TOTP após confirmar que o app autenticador está sincronizado."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    payload = decode_token(auth.split(" ", 1)[1])
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token inválido")
    user = (await db.execute(
        select(User).where(User.id == payload.get("sub"), User.is_active == True)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Execute /totp/setup primeiro")
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(req.codigo, valid_window=1):
        raise HTTPException(status_code=400, detail="Código inválido. Verifique o relógio do dispositivo.")
    user.totp_enabled = True
    await criar_audit_log(db, user.id, user.role.value, "TOTP_ATIVADO", "users", user.id, ip=obter_ip_real(request))
    await db.commit()
    return {"detail": "TOTP ativado com sucesso. Guarde o segredo em lugar seguro."}


@router.post("/totp/desativar")
async def totp_desativar(
    req: TOTPDesativarRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Desativa o TOTP após confirmar o código atual."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    payload = decode_token(auth.split(" ", 1)[1])
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token inválido")
    user = (await db.execute(
        select(User).where(User.id == payload.get("sub"), User.is_active == True)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="TOTP não está ativo")
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(req.codigo, valid_window=1):
        raise HTTPException(status_code=400, detail="Código inválido")
    user.totp_enabled = False
    user.totp_secret = None
    await criar_audit_log(db, user.id, user.role.value, "TOTP_DESATIVADO", "users", user.id, ip=obter_ip_real(request))
    await db.commit()
    return {"detail": "TOTP desativado."}
