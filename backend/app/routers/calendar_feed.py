# ── app/routers/calendar_feed.py ─────────────────────────────────────────────
# Feed ICS por advogado: audiências + prazos críticos no calendário pessoal.
# URL assinada com HMAC (sem JWT — o Google Calendar busca sozinho).
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.rate_limit import consumir
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.deadline import Deadline
from app.models.user import User
from app.services.security_service import obter_ip_real

router = APIRouter(prefix="/calendar", tags=["Calendário ICS"])
settings = get_settings()


def gerar_token_calendario(user_id: str, version: int = 1) -> str:
    """Gera credencial HMAC por usuário e versão.

    A versão 1 preserva compatibilidade com URLs antigas. A partir da primeira
    rotação, a versão passa a integrar a mensagem assinada e invalida todos os
    links anteriores daquele usuário sem afetar SECRET_KEY nem outros usuários.
    """
    mensagem = f"ics:{user_id}" if version == 1 else f"ics:{user_id}:v{version}"
    return hmac.new(
        settings.SECRET_KEY.encode(),
        mensagem.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def _url_feed(user: User) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    version = int(user.calendar_token_version or 1)
    token = gerar_token_calendario(user.id, version)
    return f"{base}/api/calendar/{user.id}/{token}.ics"


def _ics_escape(s: str) -> str:
    return (
        (s or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


async def _rl_feed_ics(request: Request) -> None:
    await consumir("calendar_ics_public_feed", f"ip:{obter_ip_real(request)}", 60)


def _headers_ics() -> dict[str, str]:
    return {
        "Cache-Control": "private, no-store, max-age=0",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": 'inline; filename="ejc-calendario.ics"',
    }


@router.get("/me/url")
async def minha_url_ics(cu: User = Depends(get_current_user)):
    """Retorna a URL vigente sem expor SECRET_KEY ou estado interno."""
    return {
        "url": _url_feed(cu),
        "version": int(cu.calendar_token_version or 1),
    }


@router.post("/me/rotate")
async def rotacionar_url_ics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Revoga imediatamente links ICS anteriores somente deste usuário."""
    cu.calendar_token_version = int(cu.calendar_token_version or 1) + 1
    await criar_audit_log(
        db,
        cu.id,
        getattr(cu.role, "value", str(cu.role)),
        "CALENDAR_ICS_ROTATED",
        "users",
        cu.id,
        detalhes=f"calendar_token_version={cu.calendar_token_version}",
        ip=obter_ip_real(request),
    )
    await db.commit()
    await db.refresh(cu)
    return {
        "detail": "Link anterior revogado.",
        "url": _url_feed(cu),
        "version": int(cu.calendar_token_version),
    }


@router.get("/{user_id}/{token}.ics", dependencies=[Depends(_rl_feed_ics)])
async def feed_ics(user_id: str, token: str):
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(
                select(User).where(
                    User.id == user_id,
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404)

        version = int(user.calendar_token_version or 1)
        esperado = gerar_token_calendario(user_id, version)
        if not hmac.compare_digest(token, esperado):
            raise HTTPException(status_code=403, detail="Token inválido ou revogado")

        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        rows = (
            await db.execute(
                select(Deadline).where(
                    Deadline.responsavel_id == user_id,
                    Deadline.deleted_at.is_(None),
                    Deadline.status == "pendente",
                    Deadline.data_prazo >= hoje,
                    Deadline.data_prazo <= hoje + timedelta(days=120),
                )
            )
        ).scalars().all()

    eventos = []
    for d in rows:
        tipo_val = getattr(d.tipo, "value", str(d.tipo))
        eh_audiencia = tipo_val == "audiencia"
        prio = getattr(d.prioridade, "value", str(d.prioridade))
        if not eh_audiencia and prio not in ("alta", "critica"):
            continue
        dt = d.data_prazo.strftime("%Y%m%d")
        emoji = "⚖️" if eh_audiencia else "⏰"
        eventos.append(
            "BEGIN:VEVENT\r\n"
            f"UID:ejc-{d.id}@depaulateixeira\r\n"
            f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"DTSTART;VALUE=DATE:{dt}\r\n"
            f"SUMMARY:{emoji} {_ics_escape(d.titulo)}\r\n"
            f"DESCRIPTION:{_ics_escape(d.base_legal or d.descricao or 'EJC')}\r\n"
            "BEGIN:VALARM\r\nTRIGGER:-P1D\r\nACTION:DISPLAY\r\n"
            "DESCRIPTION:Prazo amanhã\r\nEND:VALARM\r\n"
            "END:VEVENT\r\n"
        )

    ics = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "PRODID:-//EJC//De Paula Teixeira//PT-BR\r\n"
        f"X-WR-CALNAME:EJC — {_ics_escape(user.full_name)}\r\n"
        "X-WR-TIMEZONE:America/Sao_Paulo\r\n"
        + "".join(eventos)
        + "END:VCALENDAR\r\n"
    )
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers=_headers_ics(),
    )
