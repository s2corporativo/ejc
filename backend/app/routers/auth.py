# ── app/routers/auth.py ───────────────────────────────────────────────────────
# Autenticação: login (2FA, brute-force, must_change, device_alert),
# refresh com rotação, logout, troca de senha, reset por e-mail.
import base64
import binascii
import io
import logging
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pyotp
import qrcode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
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
from app.services import pii_crypto
from app.services.security_service import (
    esta_bloqueado, registrar_falha, limpar_falhas, obter_ip_real,
    verificar_novo_dispositivo,
    solicitar_reset, confirmar_reset,
    validar_forca_senha,
)

router  = APIRouter(prefix="/auth", tags=["Autenticação"])
settings = get_settings()
logger   = logging.getLogger("ejc.auth")

# Janela de graça da detecção de reuso de refresh (item 1 — corrida multi-aba):
# reuso do token da ÚLTIMA rotação dentro desta janela é tratado como corrida
# benigna (duas abas com o mesmo cookie / retry de rede), não como replay.
REFRESH_REUSE_GRACA_SEGUNDOS = 60

# Teto do contador do passo "TOTP obrigatório" (item 5): o fluxo em 2 etapas do
# frontend SEMPRE faz o 1º POST sem totp_code, então esse passo não pode consumir
# o orçamento principal do login (5/15min) — 5 usuários TOTP no mesmo IP de
# escritório causariam 429 geral. Contador separado por IP, teto maior, ainda
# limita sondagem de senhas válidas.
TOTP_PENDENTE_MAX_FALHAS = 20


def _papel_exige_2fa(role_value: str | None) -> bool:
    """True se o papel do usuário está na allowlist REQUIRE_2FA_ROLES (2FA
    obrigatório por política organizacional). Default (setting vazia) ⇒ sempre
    False → o comportamento atual (2FA opt-in) fica intacto."""
    if not role_value:
        return False
    return role_value.strip().lower() in settings.require_2fa_roles_list


# ─── Schemas ──────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None


class RefreshRequest(BaseModel):
    # #14: o refresh token agora trafega preferencialmente no cookie httpOnly
    # `ejc_refresh` (inacessível a JS → um XSS não rouba a sessão de 7 dias).
    # O campo no corpo continua aceito para retrocompatibilidade/clientes API.
    refresh_token: str | None = None


# ─── Cookie do refresh token (#14) ───────────────────────────────────────────
REFRESH_COOKIE = "ejc_refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        httponly=True,
        secure=(settings.APP_ENV == "production"),  # em dev (http) o browser
        samesite="lax",                              # não guardaria cookie Secure
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/")


def _refresh_from(req: RefreshRequest, request: Request) -> str:
    """Token do cookie httpOnly (preferido) ou do corpo (retrocompat)."""
    return request.cookies.get(REFRESH_COOKIE) or (req.refresh_token or "")


# ─── Segredo TOTP cifrado em repouso (auditoria pré-produção, item 4) ─────────
# O segredo é gravado cifrado (Fernet — mesma infra pii_crypto de CPF/CNPJ).
# Segredos LEGADOS gravados em claro continuam válidos: a leitura tenta decifrar
# e cai para o texto claro; no primeiro uso autenticado bem-sucedido o valor é
# re-cifrado oportunisticamente (sem migration de dados obrigatória).
def _base32_valido(secret: str) -> bool:
    """True se o valor é um segredo TOTP base32 plausível (aceito pelo pyotp)."""
    try:
        base64.b32decode(secret.upper() + "=" * (-len(secret) % 8), casefold=True)
        return True
    except (binascii.Error, ValueError):
        return False


def _totp_secret_de(user: User) -> tuple[str | None, bool]:
    """Retorna (segredo em claro p/ verificação, é_legado_em_claro).

    (None, False) quando o valor armazenado é INDECIFRÁVEL: não decifra com a
    chave atual E não é base32 válido (ex.: ciphertext gravado com uma
    PII_ENCRYPTION_KEY antiga). Antes, esse caso caía no pyotp e estourava
    binascii.Error → 500 no /login; o chamador deve responder 401/400 controlado.
    """
    try:
        return pii_crypto.decrypt(user.totp_secret), False
    except (ValueError, RuntimeError):
        pass
    secret = user.totp_secret
    if secret and _base32_valido(secret):
        return secret, True  # legado gravado em claro
    logger.error(
        "Segredo TOTP indecifrável (user=%s): não decifra com a chave atual "
        "nem é base32 legado — PII_ENCRYPTION_KEY rotacionada/ausente? "
        "O usuário precisará de reset do 2FA por um administrador.",
        getattr(user, "id", "?"),
    )
    return None, False


def _recifrar_totp_legado(user: User, secret: str, legado: bool) -> None:
    """Re-cifragem oportunista pós-verificação (mesma transação do chamador).

    Falha de cifragem (ex.: PII_ENCRYPTION_KEY ausente → RuntimeError) NUNCA
    pode derrubar um login/verificação corretos: loga e mantém o valor legado.
    """
    if legado and secret:
        try:
            user.totp_secret = pii_crypto.encrypt(secret)
        except Exception:
            logger.warning(
                "Re-cifragem oportunista do segredo TOTP falhou (user=%s) — "
                "mantido em claro. PII_ENCRYPTION_KEY ausente/inválida?",
                getattr(user, "id", "?"), exc_info=True,
            )


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
    req: LoginRequest, request: Request, response: Response,
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
            # O fluxo 2 etapas do frontend SEMPRE passa por aqui em cada login
            # TOTP legítimo — este passo NÃO consome o orçamento principal
            # (ip:/em: 5/15min), senão 5 usuários TOTP no mesmo IP de
            # escritório = 429 geral. Contador separado por IP com teto maior
            # ainda limita a sondagem de senhas válidas (o passo confirma
            # email+senha corretos); o audit preserva a trilha.
            chave_pend = f"totp_pend:{ip}"
            bloq_pend, seg_pend = esta_bloqueado(
                chave_pend, max_falhas=TOTP_PENDENTE_MAX_FALHAS)
            if bloq_pend:
                raise HTTPException(
                    status_code=429,
                    detail=f"Muitas tentativas. Tente novamente em {seg_pend//60+1} min.",
                    headers={"Retry-After": str(seg_pend)},
                )
            registrar_falha(chave_pend)
            await criar_audit_log(
                db, user.id, user.role.value, "LOGIN_TOTP_PENDENTE", "users",
                user.id, detalhes="Senha válida sem código TOTP", ip=ip,
            )
            await db.commit()
            raise HTTPException(status_code=401, detail="TOTP obrigatório. Informe o código do autenticador.")
        secret, legado = _totp_secret_de(user)
        if secret is None:
            # Segredo indecifrável (chave PII rotacionada?) — 401 controlado,
            # nunca 500. Não conta no anti-brute-force: é falha operacional
            # do servidor, não tentativa do usuário.
            await criar_audit_log(
                db, user.id, user.role.value, "LOGIN_TOTP_FALHA", "users",
                user.id, detalhes="Segredo TOTP indecifrável (chave PII?)", ip=ip,
            )
            await db.commit()
            raise HTTPException(
                status_code=401,
                detail="Autenticação de dois fatores indisponível. Contate o administrador.",
            )
        totp = pyotp.TOTP(secret)
        if not totp.verify(req.totp_code, valid_window=1):
            registrar_falha(chave_bf)
            registrar_falha(chave_em)
            await criar_audit_log(db, user.id, user.role.value, "LOGIN_TOTP_FALHA", "users", user.id, ip=ip)
            await db.commit()
            raise HTTPException(status_code=401, detail="Código TOTP inválido ou expirado")
        # Segredo legado em claro → re-grava cifrado (commit do login abaixo).
        _recifrar_totp_legado(user, secret, legado)
    user.totp_enabled = True
    await criar_audit_log(
        db, user.id, user.role.value, "TOTP_ATIVADO", "users", user.id,
        ip=obter_ip_real(request),
    )
    if payload.get("two_factor_setup_required"):
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked == False)
            .values(revoked=True, revoked_at=datetime.now(timezone.utc))
        )
        access = create_access_token(user.id, user.role.value)
        refresh_tok, jti = create_refresh_token(user.id)
        db.add(RefreshToken(
            id=str(uuid4()), user_id=user.id, jti=jti,
            expires_at=datetime.now(timezone.utc) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ))
        user.last_login_at = datetime.now(timezone.utc)
        await criar_audit_log(
            db, user.id, user.role.value, "LOGIN_2FA_CONCLUIDO", "users", user.id,
            detalhes="TOTP ativado; sessão plena emitida.",
            ip=obter_ip_real(request),
        )
        await db.commit()
        _set_refresh_cookie(response, refresh_tok)
        return {
            "detail": "TOTP ativado com sucesso.",
            "access_token": access,
            "refresh_token": refresh_tok,
            "token_type": "bearer",
            "user_id": user.id,
            "full_name": user.full_name,
            "role": user.role.value,
        }
    await db.commit()
    return {"detail": "TOTP ativado com sucesso. Guarde o segredo em lugar seguro."}


@router.post("/totp/desativar")
@limiter.limit("10/minute")
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
        select(User).where(
            User.id == payload.get("sub"),
            User.is_active == True,
            User.deleted_at.is_(None),  # item 10: mesmo filtro do get_current_user
        )
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="TOTP não está ativo")
    # Enforcement por papel (REQUIRE_2FA_ROLES): um usuário cujo papel é OBRIGADO
    # a usar 2FA não pode se auto-desproteger. Recusa ANTES de qualquer
    # verificação de código — nem com o código correto o 2FA é removido. Default
    # (setting vazia) ⇒ nunca bloqueia; comportamento atual preservado.
    if _papel_exige_2fa(user.role.value):
        raise HTTPException(
            status_code=403,
            detail="Seu perfil exige autenticação de dois fatores. A desativação "
                   "do 2FA não é permitida para este papel. Contate o administrador.",
        )
    # Anti-brute-force com chave PRÓPRIA (não ip:/em: do login): um atacante
    # com access token roubado adivinhando códigos aqui NÃO pode trancar o
    # /login legítimo da vítima — e o bloqueio deste endpoint não depende do IP.
    chave_totp = f"totp_desativar:{user.email.lower()}"
    bloqueado, seg = esta_bloqueado(chave_totp)
    if bloqueado:
        raise HTTPException(
            status_code=429,
            detail=f"Muitas tentativas. Tente novamente em {seg//60+1} min.",
            headers={"Retry-After": str(seg)},
        )
    secret, _legado = _totp_secret_de(user)
    if secret is None:
        raise HTTPException(
            status_code=400,
            detail="Segredo TOTP ilegível — contate o administrador para reset do 2FA.",
        )
    totp = pyotp.TOTP(secret)
    if not totp.verify(req.codigo, valid_window=1):
        # Código TOTP inválido conta no anti-brute-force (chave própria acima) —
        # este endpoint autenticado permitia adivinhar o código sem custo.
        registrar_falha(chave_totp)
        raise HTTPException(status_code=400, detail="Código inválido")
    limpar_falhas(chave_totp)
    user.totp_enabled = False
    user.totp_secret = None
    await criar_audit_log(db, user.id, user.role.value, "TOTP_DESATIVADO", "users", user.id, ip=obter_ip_real(request))
    await db.commit()
    return {"detail": "TOTP desativado."}
