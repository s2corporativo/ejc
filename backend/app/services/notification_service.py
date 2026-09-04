# ── app/services/notification_service.py ─────────────────────────────────────
# Notificações: interna (sino) + email (SMTP) + push (VAPID) + WhatsApp
# (Evolution API — a MESMA instância que já atendia o webhook de ENTRADA passa a
# ser também o remetente de SAÍDA). Todo canal externo é opt-in por .env e
# degrada em silêncio: falha de canal nunca sobe para quem chamou.
from __future__ import annotations
import asyncio
import logging
import re
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.notification import Notification
from app.services.notification_preferences import (
    MANDATORY_INTERNAL_TYPES,
    category_enabled,
    channel_availability,
    get_notification_preference,
    is_quiet_hours,
)

logger = logging.getLogger(__name__)
settings = get_settings()


async def criar_notificacao_interna(
    db: AsyncSession, user_id: str, titulo: str, mensagem: str,
    tipo: str = "sistema", link: str | None = None,
) -> Notification:
    """Cria notificação no sino do header. Sempre funciona (sem API externa)."""
    n = Notification(
        id=str(uuid4()), user_id=user_id,
        titulo=titulo, mensagem=mensagem, tipo=tipo, link=link,
    )
    db.add(n)
    await db.commit()
    return n


# ── WhatsApp (Evolution API) ──────────────────────────────────────────────────
# LGPD: telefone e conteúdo da mensagem são dado pessoal/sigilo profissional —
# NUNCA vão para o log. O que se registra é o número mascarado (4 últimos
# dígitos) e o TAMANHO da mensagem, o bastante para diagnosticar entrega.
def _mascarar_telefone(numero: str) -> str:
    """`***1234` — só os 4 últimos dígitos chegam ao log (LGPD)."""
    d = re.sub(r"\D", "", numero or "")
    return f"***{d[-4:]}" if len(d) >= 4 else "***"


def normalizar_telefone_br(telefone: str | None) -> str | None:
    """E.164 SEM "+" (formato que a Evolution API espera em `number`).

    Mantém só os dígitos, descarta o prefixo internacional discado (`00`) e
    acrescenta o DDI 55 quando falta — 10 dígitos (fixo com DDD) ou 11
    (celular com DDD). Número já normalizado (`5531...`) passa intacto, e DDI
    estrangeiro é preservado. Devolve None quando não resta número plausível,
    para o envio degradar em vez de bater na API com lixo.
    """
    digitos = re.sub(r"\D", "", telefone or "")
    if digitos.startswith("00"):
        digitos = digitos[2:]
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    if not 12 <= len(digitos) <= 15:
        return None
    return digitos


async def enviar_whatsapp(telefone: str, mensagem: str) -> bool:
    """Envia WhatsApp pela Evolution API. Falha silenciosa (nunca propaga).

    Opt-in triplo: `WHATSAPP_ENABLED=true` + `EVOLUTION_API_URL` +
    `EVOLUTION_API_KEY`. Faltando qualquer um, retorna False SEM tocar a rede —
    o alerta segue pelo sino interno. `notificar` já gateia o canal por
    `channel_availability().whatsapp`, que calcula a mesma condição; a
    checagem aqui é a garantia para quem chama a função direta.
    """
    if not settings.WHATSAPP_ENABLED:
        return False
    base = (settings.EVOLUTION_API_URL or "").strip().rstrip("/")
    chave = (settings.EVOLUTION_API_KEY or "").strip()
    instancia = (settings.EVOLUTION_INSTANCE or "").strip()
    if not base or not chave or not instancia:
        logger.info(
            "WhatsApp: Evolution API não configurada (URL/chave/instância) — "
            "envio ignorado."
        )
        return False

    numero = normalizar_telefone_br(telefone)
    if not numero:
        logger.warning("WhatsApp: telefone inválido — envio ignorado.")
        return False

    url = f"{base}/message/sendText/{instancia}"
    try:
        async with httpx.AsyncClient(timeout=settings.EVOLUTION_TIMEOUT) as client:
            resposta = await client.post(
                url,
                headers={"apikey": chave, "Content-Type": "application/json"},
                json={"number": numero, "text": mensagem},
            )
            resposta.raise_for_status()
    except httpx.HTTPStatusError as e:
        # Só o código HTTP: o corpo da resposta da Evolution ecoa o payload
        # (número + texto) e não pode ir para o log.
        logger.warning(
            "WhatsApp: Evolution API recusou o envio para %s (HTTP %s).",
            _mascarar_telefone(numero), e.response.status_code,
        )
        return False
    except Exception as e:  # noqa: BLE001 — timeout/DNS/conexão: degrada
        logger.warning(
            "WhatsApp: envio para %s falhou (%s).",
            _mascarar_telefone(numero), type(e).__name__,
        )
        return False

    logger.info(
        "WhatsApp enviado para %s (%d caracteres).",
        _mascarar_telefone(numero), len(mensagem or ""),
    )
    return True


async def enviar_email(destinatario: str, assunto: str, corpo: str) -> bool:
    """Email via SMTP (smtplib em thread). Falha silenciosa."""
    if not settings.EMAIL_ENABLED:
        return False
    import smtplib
    from email.mime.text import MIMEText

    def _send():
        msg = MIMEText(corpo, "html", "utf-8")
        msg["Subject"] = assunto
        msg["From"] = settings.SMTP_USER
        msg["To"] = destinatario
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
            s.starttls()
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(msg)

    try:
        await asyncio.to_thread(_send)
        return True
    except Exception as e:
        logger.error(f"SMTP falhou: {e}")
        return False


# ── Web Push (PWA) ────────────────────────────────────────────────────────────
# SSRF guard: o `endpoint` do push é fornecido pelo cliente em /push/subscribe.
# Sem allowlist, o servidor pode ser induzido a fazer POST a uma URL interna
# arbitrária (ex.: 169.254.169.254, serviço interno). Só aceitamos https dos
# serviços de push conhecidos (Chrome/Android FCM, Firefox/Mozilla, Safari/Apple,
# Edge/WNS). Validado no schema (422 na inscrição) E revalidado no envio.
_PUSH_HOSTS_PERMITIDOS = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "updates.push.services.mozilla.com",
    "web.push.apple.com",
    "notify.windows.com",
)


def endpoint_push_valido(url: str) -> bool:
    from urllib.parse import urlparse
    try:
        u = urlparse(url or "")
    except Exception:
        return False
    if u.scheme != "https" or not u.hostname:
        return False
    host = u.hostname.lower()
    return any(host == d or host.endswith("." + d) for d in _PUSH_HOSTS_PERMITIDOS)


async def enviar_push(db, user_id: str, titulo: str, mensagem: str, link: str = "/"):
    """Envia push a todas as subscriptions do usuário. Falha silenciosa."""
    if not settings.PUSH_ENABLED or not settings.VAPID_PRIVATE_KEY:
        return
    try:
        from pywebpush import webpush, WebPushException
        from sqlalchemy import select, delete
        from app.models.push import PushSubscription
        import json as _json

        _vapid_pem = settings.VAPID_PRIVATE_KEY
        if _vapid_pem and "BEGIN" not in _vapid_pem:
            import base64 as _b64
            try:
                _vapid_pem = _b64.b64decode(_vapid_pem).decode()
            except Exception:
                # Não era base64 — segue com o valor original (fail-soft), mas
                # registra: chave VAPID malformada faz o push falhar depois.
                logger.warning(
                    "Push: VAPID_PRIVATE_KEY sem 'BEGIN' e não decodificável como "
                    "base64 — usando valor original.",
                    exc_info=True,
                )

        subs = (await db.execute(
            select(PushSubscription).where(PushSubscription.user_id == user_id)
        )).scalars().all()

        for s in subs:
            # Defesa em profundidade: nunca faz POST a endpoint fora da allowlist
            # (mesmo que algo tenha sido gravado antes do guard do schema existir).
            if not endpoint_push_valido(s.endpoint):
                logger.warning("Push: endpoint fora da allowlist ignorado (SSRF guard)")
                continue
            try:
                await asyncio.to_thread(
                    webpush,
                    subscription_info={
                        "endpoint": s.endpoint,
                        "keys": {"p256dh": s.p256dh, "auth": s.auth},
                    },
                    data=_json.dumps({"title": titulo, "body": mensagem, "url": link}),
                    vapid_private_key=_vapid_pem,
                    vapid_claims={"sub": settings.VAPID_CLAIM_EMAIL},
                )
            except WebPushException as e:
                # 404/410 = subscription morta → limpar
                if e.response is not None and e.response.status_code in (404, 410):
                    await db.execute(delete(PushSubscription)
                                     .where(PushSubscription.id == s.id))
                    # Sem commit, a limpeza da subscription morta seria descartada
                    # ao fechar a sessão — o endpoint tentaria o mesmo push morto
                    # em toda notificação seguinte.
                    await db.commit()
                else:
                    logger.warning(f"Push falhou: {e}")
    except Exception as e:
        logger.warning(f"Push indisponível: {e}")


# ── Dispatch unificado (respeita preferências) ────────────────────────────────
async def notificar(
    db: AsyncSession,
    user_id: str,
    titulo: str,
    mensagem: str,
    *,
    tipo: str = "sistema",
    link: str | None = None,
    email: str | None = None,
    telefone: str | None = None,
    email_assunto: str | None = None,
    email_corpo: str | None = None,
    forcar_sino: bool = False,
) -> None:
    """Ponto ÚNICO de entrega de notificações — consulta as preferências do
    usuário antes de disparar cada canal (P1: as preferências deixam de ser
    inertes).

    Semântica (respeita sigilo jurídico):
      - Sino interno: criado se o tipo é mandatório, a categoria está ativa OU
        `forcar_sino=True`. Alertas críticos (mandatórios) SEMPRE geram o sino,
        mesmo com a categoria desativada. `forcar_sino` é para alertas
        OPERACIONAIS internos que são um item de trabalho e não devem sumir por
        preferência (ex.: régua de cobrança) — força só o sino, sem forçar
        canais externos. Se não-mandatório, categoria desativada e sem
        `forcar_sino`, nada é criado e nenhum canal externo dispara.
      - Quiet hours (por preferência/timezone): suprime TODOS os canais
        externos; o sino já foi criado (não é afetado).
      - Canais externos (push/email/whatsapp): só quando a categoria está ativa
        (ou o tipo é mandatório), o canal está disponível no ambiente E
        habilitado na preferência (ou sem preferência). `forcar_sino` NÃO abre
        canais externos — apenas garante o registro interno.
      - Falha de um canal externo nunca derruba os demais nem o fluxo.
    """
    pref = await get_notification_preference(db, user_id)
    mandatory = tipo in MANDATORY_INTERNAL_TYPES
    cat_ok = category_enabled(pref, tipo)

    # ── Sino interno (nunca afetado por quiet hours) ──────────────────────────
    if mandatory or cat_ok or forcar_sino:
        try:
            await criar_notificacao_interna(
                db, user_id, titulo, mensagem, tipo=tipo, link=link,
            )
        except Exception as e:
            logger.warning(f"[notificar] sino falhou (user={user_id}): {e}")

    # Canais externos exigem categoria ativa (mandatório ignora a categoria).
    # `forcar_sino` garante só o registro interno, nunca canais externos.
    if not mandatory and not cat_ok:
        return

    # ── Quiet hours suprime canais externos (não o sino) ──────────────────────
    if pref is not None:
        try:
            tz = ZoneInfo(pref.timezone or "America/Sao_Paulo")
        except Exception:
            tz = ZoneInfo("America/Sao_Paulo")
        if is_quiet_hours(
            datetime.now(tz), pref.quiet_hours_start, pref.quiet_hours_end
        ):
            return

    avail = channel_availability()

    # ── Push ──────────────────────────────────────────────────────────────────
    if avail.push and (pref is None or pref.push_enabled):
        try:
            await enviar_push(db, user_id, titulo, mensagem, link or "/")
        except Exception as e:
            logger.warning(f"[notificar] push falhou (user={user_id}): {e}")

    # ── E-mail ────────────────────────────────────────────────────────────────
    if email and avail.email and (pref is None or pref.email_enabled):
        try:
            await enviar_email(
                email,
                email_assunto or f"[EJC] {titulo}",
                email_corpo or f"<p>{mensagem}</p>",
            )
        except Exception as e:
            logger.warning(f"[notificar] email falhou (user={user_id}): {e}")

    # ── WhatsApp ──────────────────────────────────────────────────────────────
    if telefone and avail.whatsapp and (pref is None or pref.whatsapp_enabled):
        try:
            await enviar_whatsapp(telefone, f"{titulo}\n\n{mensagem}")
        except Exception as e:
            logger.warning(f"[notificar] whatsapp falhou (user={user_id}): {e}")
