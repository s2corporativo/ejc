# ── app/routers/auth.py ───────────────────────────────────────────────────────
# Autenticação: login (2FA, brute-force, must_change, device_alert),
# refresh com rotação, logout, troca de senha, reset por e-mail.
import base64
import binascii
import logging
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pyotp

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

    # #14: entrega o refresh token no cookie httpOnly (não legível por JS).
    _set_refresh_cookie(response, refresh_tok)

    resp = {
        "access_token": access, "refresh_token": refresh_tok,
        "token_type": "bearer",
        "user_id": user.id, "full_name": user.full_name, "role": user.role.value,
    }
    # ── 5. Sinalizar troca obrigatória de senha ──────────────────────
    if user.must_change_password:
        resp["must_change_password"] = True
        resp["detail"] = "Troca de senha obrigatória antes de continuar."
    # ── 6. 2FA obrigatório por papel (enforcement SEM lockout) ────────
    # Se o papel exige 2FA (REQUIRE_2FA_ROLES) e o usuário ainda não tem TOTP
    # ativo, sinaliza ao frontend que ele PRECISA configurar — sem bloquear o
    # login (não há coluna/migration nova; ninguém é trancado). Default vazio
    # ⇒ nunca dispara e a resposta fica idêntica à atual.
    if _papel_exige_2fa(user.role.value) and not user.totp_enabled:
        resp["precisa_configurar_2fa"] = True
    return resp


# ─── Refresh (rotação de token) ───────────────────────────────────────────────
@router.post("/refresh")
@limiter.limit("20/minute")
async def refresh(req: RefreshRequest, request: Request, response: Response,
                  db: AsyncSession = Depends(get_db)):
    token = _refresh_from(req, request)
    payload = decode_token(token) if token else None
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token inválido")

    jti = payload.get("jti")
    user_id = payload.get("sub")
    record = (await db.execute(
        select(RefreshToken).where(RefreshToken.jti == jti)
    )).scalar_one_or_none()

    # ── Detecção de REUSO (item 1 — auditoria pré-produção; OAuth 2.0 Security
    # BCP §4.14.2): token criptograficamente VÁLIDO cujo JTI já foi revogado
    # (rotação anterior) ou nunca foi registrado = replay. Ex.: atacante roubou
    # o refresh e rotacionou primeiro — antes, a cadeia dele continuava válida
    # por 7 dias. Resposta padrão: revogar TODAS as sessões do `sub` (derruba
    # também a cadeia do atacante) + trilha de auditoria.
    #
    # EXCEÇÃO (corrida multi-aba, pré-go-live item 1): duas abas compartilham o
    # cookie `ejc_refresh`; um refresh concorrente faz a 2ª chegar com o token
    # que a 1ª acabou de rotacionar. Reuso do token da ÚLTIMA rotação
    # (replaced_by_jti aponta para token AINDA ATIVO) dentro da janela de graça
    # → 401 simples, sem revogação em massa e SEM limpar o cookie (o browser já
    # tem o token novo da outra aba). Token de rotação mais antiga (substituto
    # já revogado) ou fora da graça → punição total normal.
    if record is None or record.revoked:
        agora = datetime.now(timezone.utc)
        if (
            record is not None
            and record.revoked_at is not None
            and record.replaced_by_jti
            and (agora - record.revoked_at).total_seconds() <= REFRESH_REUSE_GRACA_SEGUNDOS
        ):
            substituto = (await db.execute(
                select(RefreshToken).where(
                    RefreshToken.jti == record.replaced_by_jti)
            )).scalar_one_or_none()
            if substituto is not None and not substituto.revoked:
                raise HTTPException(
                    status_code=401,
                    detail="Sessão atualizada em outra aba — tente novamente",
                )
        # Token revogado SEM replaced_by_jti nunca foi rotacionado: foi encerrado
        # por logout ou troca de senha. O replay vem de um dispositivo antigo
        # legítimo, não é o sinal de furto do BCP §4.14.2 — 401 simples, sem
        # cascata de revogação e sem marcar REFRESH_REUSE na auditoria.
        if record is not None and not record.replaced_by_jti:
            # M-S3: mesmo sem cascata, o replay pós-logout precisa de trilha —
            # um dispositivo reapresentando token encerrado é sinal fraco de
            # comprometimento que a forense cruza com IP/frequência. Padrão
            # leve do REFRESH_REUSE abaixo, sem revogação em massa.
            await criar_audit_log(
                db, user_id, None, "REFRESH_REPLAY_POS_LOGOUT", "users", user_id,
                detalhes=f"Refresh revogado sem rotação reapresentado (jti={jti}) "
                         "— sessão encerrada por logout/troca de senha; negado "
                         "sem cascata de revogação.",
                ip=obter_ip_real(request),
            )
            await db.commit()
            _clear_refresh_cookie(response)
            raise HTTPException(
                status_code=401,
                detail="Sessão encerrada. Faça login novamente.",
            )
        ip = obter_ip_real(request)
        if user_id:
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == user_id,
                       RefreshToken.revoked == False)
                .values(revoked=True, revoked_at=agora)
            )
            await criar_audit_log(
                db, user_id, None, "REFRESH_REUSE", "users", user_id,
                detalhes=f"Reuso de refresh token detectado (jti={jti}) — "
                         "todas as sessões do usuário foram revogadas.",
                ip=ip,
            )
            await db.commit()
        else:
            # Item 9: payload válido SEM `sub` é anômalo (token forjado com a
            # chave vazada ou bug de emissão) — precisa aparecer na auditoria
            # mesmo sem haver sessões a revogar.
            await criar_audit_log(
                db, None, None, "REFRESH_REUSE", "users", None,
                detalhes=f"Reuso de refresh token SEM sub no payload "
                         f"(jti={jti}) — anômalo; nenhuma sessão a revogar.",
                ip=ip,
            )
            await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Token revogado ou expirado")

    if record.expires_at <= datetime.now(timezone.utc):
        # Expiração natural não é reuso — nega sem punir as demais sessões.
        raise HTTPException(status_code=401, detail="Token revogado ou expirado")

    # Rotação: revogar o atual, emitir novo par (revoked_at/replaced_by_jti
    # alimentam a janela de graça da detecção de reuso acima)
    record.revoked = True
    record.revoked_at = datetime.now(timezone.utc)

    user = (await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_active == True,
            User.deleted_at.is_(None),  # item 10: mesmo filtro do get_current_user
        )
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário inativo")

    # Propaga o estado de troca obrigatória: sem isto, um usuário com senha
    # temporária (must_change_password) obteria via /refresh um access token
    # SEM o claim pwd_change_required, contornando o gate de troca de senha.
    new_access = create_access_token(
        user.id, user.role.value,
        must_change_password=user.must_change_password,
    )
    new_refresh, new_jti = create_refresh_token(user.id)
    record.replaced_by_jti = new_jti

    db.add(RefreshToken(
        id=str(uuid4()), user_id=user.id, jti=new_jti,
        expires_at=datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.commit()

    # Rotaciona também o cookie httpOnly com o novo refresh token.
    _set_refresh_cookie(response, new_refresh)
    return {"access_token": new_access, "refresh_token": new_refresh,
            "token_type": "bearer"}


# ─── Logout ───────────────────────────────────────────────────────────────────
@router.post("/logout")
async def logout(req: RefreshRequest, request: Request, response: Response,
                 db: AsyncSession = Depends(get_db)):
    token = _refresh_from(req, request)
    payload = decode_token(token) if token else None
    if payload:
        jti = payload.get("jti")
        if jti:
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.jti == jti)
                .values(revoked=True)
            )
            await db.commit()
    _clear_refresh_cookie(response)
    return {"detail": "Logout realizado"}


# ─── Alterar senha (autenticado) ──────────────────────────────────────────────
@router.post("/alterar-senha")
@limiter.limit("10/minute")
async def alterar_senha(
    req: AlterarSenhaRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # Recria o fluxo manualmente para aceitar token must_change
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    token = auth.split(" ", 1)[1]
    payload = decode_token(token)
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

    if not verify_password(req.senha_atual, user.hashed_password):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")

    # Política de senha forte — só na DEFINIÇÃO da senha nova (não no login),
    # para não trancar quem já tem senha curta legada.
    try:
        validar_forca_senha(req.nova_senha, user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user.hashed_password      = get_password_hash(req.nova_senha)
    user.must_change_password = False

    # Revogar TODAS as outras sessões (segurança pós-troca). revoked_at marca
    # o instante para a trilha forense; replaced_by_jti fica nulo de propósito —
    # é o que distingue revogação administrativa de rotação no /refresh.
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked == False)
        .values(revoked=True, revoked_at=datetime.now(timezone.utc))
    )

    # P0 usabilidade (2026-07-18, §2.3): manter a sessão ATUAL após a troca —
    # emite novos tokens (mesmo formato do /login) com o claim must_change_password
    # já limpo, para o frontend continuar logado sem voltar ao /login. As demais
    # sessões seguem revogadas acima; o refresh novo nasce DEPOIS da revogação.
    access = create_access_token(user.id, user.role.value,
                                 must_change_password=False)
    refresh_tok, jti = create_refresh_token(user.id)
    db.add(RefreshToken(
        id=str(uuid4()), user_id=user.id, jti=jti,
        expires_at=datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))

    await criar_audit_log(
        db, user.id, user.role.value, "TROCA_SENHA", "users", user.id,
        ip=obter_ip_real(request),
    )
    await db.commit()

    # Rotaciona o cookie httpOnly com o refresh da sessão que permanece viva.
    _set_refresh_cookie(response, refresh_tok)
    return {
        # Compat: o campo `detail` continua existindo (texto atualizado — a
        # sessão não é mais derrubada).
        "detail": "Senha alterada com sucesso.",
        "access_token": access,
        "refresh_token": refresh_tok,
        "token_type": "bearer",
        "user_id": user.id,
        "full_name": user.full_name,
        "role": user.role.value,
        "must_change_password": False,
    }


# ─── Recuperação de senha (público) ──────────────────────────────────────────
@router.post("/recuperar-senha")
@limiter.limit("3/hour")
async def recuperar_senha(
    req: ResetSolicitarRequest, request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = obter_ip_real(request)

    # P0 usabilidade (2026-07-18, §2.2): com SMTP desligado (instalação padrão)
    # a resposta neutra vira beco sem saída — o e-mail nunca chega. Mesma
    # detecção do security_service.enviar_email (EMAIL_ENABLED + SMTP_USER).
    # A mensagem é IGUAL para qualquer e-mail (não vaza existência de conta).
    if not settings.EMAIL_ENABLED or not settings.SMTP_USER:
        logger.warning(
            "Recuperação de senha solicitada com envio de e-mail desligado "
            "(EMAIL_ENABLED/SMTP_USER) — orientado a procurar o administrador."
        )
        return {
            "detail": (
                "O envio de e-mail não está configurado nesta instalação. "
                "Procure o administrador do escritório para redefinir sua senha."
            )
        }

    await solicitar_reset(db, req.email, ip)
    return {"detail": "Se o e-mail existir, enviaremos as instruções em breve."}


@router.post("/redefinir-senha")
@limiter.limit("10/hour")
async def redefinir_senha(
    req: ResetConfirmarRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        ok = await confirmar_reset(db, req.token, req.nova_senha)
    except ValueError as e:
        # Token válido, porém senha nova fraca (política de senha forte):
        # mensagem específica em vez do genérico "link inválido".
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Link inválido ou expirado. Solicite um novo.",
        )
    return {"detail": "Senha redefinida com sucesso. Faça login."}


# ─── TOTP: Setup ──────────────────────────────────────────────────────────────
@router.post("/totp/setup")
@limiter.limit("10/minute")
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
        select(User).where(
            User.id == payload.get("sub"),
            User.is_active == True,
            User.deleted_at.is_(None),  # item 10: mesmo filtro do get_current_user
        )
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="TOTP já está ativo. Desative antes de reconfigurar.")
    secret = pyotp.random_base32()
    # Item 4: em repouso o segredo vai CIFRADO (Fernet — pii_crypto). O valor em
    # claro só aparece na resposta deste setup (QR code) e nunca mais.
    user.totp_secret = pii_crypto.encrypt(secret)
    await db.commit()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name="EJC — De Paula Teixeira")
    return {"secret": secret, "uri": uri, "aviso": "Use /totp/verificar com o primeiro código para ativar."}


@router.post("/totp/verificar")
@limiter.limit("10/minute")
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
        select(User).where(
            User.id == payload.get("sub"),
            User.is_active == True,
            User.deleted_at.is_(None),  # item 10: mesmo filtro do get_current_user
        )
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Execute /totp/setup primeiro")
    secret, legado = _totp_secret_de(user)
    if secret is None:
        raise HTTPException(
            status_code=400,
            detail="Segredo TOTP ilegível — execute /totp/setup novamente.",
        )
    totp = pyotp.TOTP(secret)
    if not totp.verify(req.codigo, valid_window=1):
        raise HTTPException(status_code=400, detail="Código inválido. Verifique o relógio do dispositivo.")
    _recifrar_totp_legado(user, secret, legado)
    user.totp_enabled = True
    await criar_audit_log(db, user.id, user.role.value, "TOTP_ATIVADO", "users", user.id, ip=obter_ip_real(request))
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
