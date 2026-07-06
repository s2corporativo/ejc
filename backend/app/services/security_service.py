# ── app/services/security_service.py ─────────────────────────────────────────
# Funções de segurança operacional:
#   1. Anti-brute-force (contador em memória — compatível com --workers 1)
#   2. Alerta de login em novo dispositivo (IP desconhecido)
#   3. Envio de e-mail via Gmail SMTP (TLS, porta 587)
#   4. Reset de senha: gera token + envia e-mail + valida + aplica
from __future__ import annotations
import asyncio
import hashlib
import logging
import secrets
import smtplib
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models.user import User
from app.models.password_reset import PasswordResetToken, UserKnownIP
from app.models.notification import Notification

settings = get_settings()
logger = logging.getLogger("ejc.security")

# ── Anti-brute-force (em memória, ok para worker único) ──────────────────────
# Estrutura: {chave: [timestamps de falhas]}
_falhas: dict[str, list[datetime]] = defaultdict(list)
JANELA_SEGUNDOS   = 15 * 60   # janela de 15 minutos
MAX_FALHAS        = 5          # tentativas antes do bloqueio
BLOQUEIO_SEGUNDOS = 15 * 60   # duração do bloqueio


def obter_ip_real(request) -> str:
    """
    IP real do cliente respeitando proxy reverso (Nginx).
    Sem isto, atrás do Nginx todos os IPs viram 127.0.0.1 e o
    anti-brute-force bloquearia o escritório inteiro.

    Usa o ÚLTIMO salto do X-Forwarded-For (o posto pelo nosso Nginx), não o
    primeiro — o primeiro é controlado pelo cliente e era spoofável. Lógica
    centralizada em request_context.parse_client_ip.
    """
    from app.core.request_context import parse_client_ip
    return parse_client_ip(
        request.headers.get("x-forwarded-for", ""),
        request.headers.get("x-real-ip", ""),
        request.client.host if request.client else None,
    )


def registrar_falha(chave: str) -> None:
    agora = datetime.now(timezone.utc)
    _falhas[chave].append(agora)
    # Limpar entradas antigas para não crescer indefinidamente
    corte = agora - timedelta(seconds=JANELA_SEGUNDOS)
    _falhas[chave] = [t for t in _falhas[chave] if t > corte]


def esta_bloqueado(chave: str) -> tuple[bool, int]:
    """Retorna (bloqueado, segundos_restantes)."""
    agora = datetime.now(timezone.utc)
    corte = agora - timedelta(seconds=JANELA_SEGUNDOS)
    recentes = [t for t in _falhas.get(chave, []) if t > corte]
    if len(recentes) >= MAX_FALHAS:
        mais_antiga = min(recentes)
        restante = int((mais_antiga + timedelta(seconds=BLOQUEIO_SEGUNDOS)
                        - agora).total_seconds())
        return True, max(0, restante)
    return False, 0


def limpar_falhas(chave: str) -> None:
    _falhas.pop(chave, None)


# ── Email via Gmail (SMTP TLS 587) ───────────────────────────────────────────
def _smtp_chave_login() -> tuple[str, str]:
    """Usuário Gmail configurado no .env."""
    return settings.SMTP_USER, settings.SMTP_PASSWORD


def _html_base(titulo: str, corpo: str) -> str:
    navy, gold = "#0f1f3d", "#c9a94e"
    return f"""<!DOCTYPE html><html><body style="margin:0;background:#f1f5f9;font-family:Arial,sans-serif">
<div style="max-width:520px;margin:32px auto;background:#fff;border-radius:12px;overflow:hidden;
     box-shadow:0 2px 8px rgba(0,0,0,.1)">
  <div style="background:{navy};padding:24px 32px;text-align:center">
    <div style="color:{gold};font-size:22px;font-weight:bold;letter-spacing:1px">
      De Paula Teixeira<br><span style="font-size:13px;opacity:.8">Advogados</span>
    </div>
  </div>
  <div style="padding:32px">{corpo}</div>
  <div style="background:#f8fafc;padding:14px 32px;font-size:11px;color:#888;text-align:center">
    EJC — Ecossistema Jurídico · Betim/MG · Este e-mail é automático.
  </div>
</div></body></html>"""


async def enviar_email(destinatario: str, assunto: str, html: str) -> bool:
    """Envio assíncrono (run_in_executor p/ não bloquear o event loop)."""
    if not settings.EMAIL_ENABLED or not settings.SMTP_USER:
        logger.info(f"[Email OFF] {assunto} → {destinatario}")
        return False

    def _send():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[EJC] {assunto}"
        msg["From"]    = f"EJC · De Paula Teixeira <{settings.SMTP_USER}>"
        msg["To"]      = destinatario
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
            s.ehlo(); s.starttls(); s.ehlo()
            s.login(*_smtp_chave_login())
            s.sendmail(settings.SMTP_USER, destinatario, msg.as_string())

    try:
        await asyncio.get_event_loop().run_in_executor(None, _send)
        logger.info(f"Email enviado: {assunto} → {destinatario}")
        return True
    except Exception as e:
        logger.error(f"Falha no email: {e}")
        return False


# ── Recuperação de senha ──────────────────────────────────────────────────────
async def solicitar_reset(db: AsyncSession, email: str, ip: str | None) -> bool:
    """
    Gera token de reset e envia por e-mail. Retorna True sempre
    (não revela se o e-mail existe — segurança contra enumeração).
    """
    user = (await db.execute(
        select(User).where(User.email == email.lower(),
                           User.is_active == True,
                           User.deleted_at.is_(None))
    )).scalar_one_or_none()

    if not user:
        return True  # silencioso

    token_raw  = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_raw.encode()).hexdigest()

    db.add(PasswordResetToken(
        id=str(uuid4()), user_id=user.id,
        token_hash=token_hash, ip_solicitante=ip,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    ))
    await db.commit()

    link = f"{settings.FRONTEND_URL}/redefinir-senha?token={token_raw}"
    corpo = f"""
<h2 style="color:#0f1f3d;margin-top:0">Redefinição de senha</h2>
<p>Recebemos uma solicitação para redefinir a senha da sua conta no EJC.</p>
<p><a href="{link}" style="display:inline-block;background:#0f1f3d;color:#c9a94e;
   padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold">
  Redefinir senha</a></p>
<p style="color:#888;font-size:13px">O link expira em <strong>30 minutos</strong>.
   Se não foi você, ignore este e-mail.</p>"""
    await enviar_email(user.email, "Redefinição de senha", _html_base("Reset", corpo))
    return True


async def confirmar_reset(db: AsyncSession, token_raw: str, nova_senha: str) -> bool:
    """Valida token e aplica nova senha. Revoga todas as sessões."""
    token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
    record = (await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
    )).scalar_one_or_none()

    if not record:
        return False

    user = (await db.execute(
        select(User).where(User.id == record.user_id)
    )).scalar_one_or_none()
    if not user:
        return False

    user.hashed_password     = get_password_hash(nova_senha)
    user.must_change_password = False
    record.used = True

    # Revogar todas as sessões ativas (segurança pós-reset)
    from app.models.user import RefreshToken
    from sqlalchemy import update
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked == False)
        .values(revoked=True)
    )
    # As chaves de brute-force são prefixadas ("em:{email}"/"ip:{ip}", ver
    # routers/auth.py). Limpar por e-mail cru NÃO casava nenhuma chave.
    limpar_falhas(f"em:{user.email.lower()}")
    await db.commit()
    return True


# ── Alerta de login em novo dispositivo ──────────────────────────────────────
async def verificar_novo_dispositivo(
    db: AsyncSession, user: User, ip: str | None, user_agent: str | None,
) -> None:
    """
    Se o IP nunca foi visto para este usuário: registra e envia notificação + e-mail.
    Opera de forma assíncrona — falha silenciosa (não bloqueia o login).
    """
    if not ip:
        return

    ua_hash = hashlib.md5((user_agent or "").encode()).hexdigest()[:16]

    existe = (await db.execute(
        select(UserKnownIP).where(
            UserKnownIP.user_id == user.id,
            UserKnownIP.ip == ip,
        )
    )).scalar_one_or_none()

    if not existe:
        db.add(UserKnownIP(
            id=str(uuid4()), user_id=user.id,
            ip=ip, user_agent_hash=ua_hash,
        ))
        agora_fmt = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

        # Notificação interna (sino)
        db.add(Notification(
            id=str(uuid4()), user_id=user.id,
            titulo="🔐 Login em novo dispositivo",
            mensagem=f"IP {ip} · {agora_fmt}. Se não foi você, altere sua senha.",
            tipo="seguranca", link="/configuracoes",
        ))

        # E-mail de alerta
        corpo = f"""
<h2 style="color:#0f1f3d;margin-top:0">🔐 Login em novo dispositivo</h2>
<p>Detectamos um acesso à sua conta EJC a partir de um endereço IP nunca visto antes.</p>
<table style="border-collapse:collapse;width:100%;font-size:14px">
  <tr><td style="padding:6px;color:#666">IP</td>
      <td style="padding:6px;font-weight:bold">{ip}</td></tr>
  <tr><td style="padding:6px;color:#666">Data/Hora</td>
      <td style="padding:6px;font-weight:bold">{agora_fmt}</td></tr>
</table>
<p style="margin-top:18px">Se não foi você, <strong>troque sua senha imediatamente</strong>
e entre em contato com o administrador do sistema.</p>"""
        await enviar_email(
            user.email, "Login em novo dispositivo",
            _html_base("Alerta de segurança", corpo),
        )
