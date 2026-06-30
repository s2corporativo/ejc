# ── app/routers/calendar_feed.py ─────────────────────────────────────────────
# Feed ICS por advogado: audiências + prazos críticos no calendário pessoal.
# URL assinada com HMAC (sem JWT — o Google Calendar busca sozinho).
# Assinar no Google: Configurações → Adicionar agenda → Por URL.
from __future__ import annotations
import hashlib
import hmac
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.deadline import Deadline
from app.models.user import User

router = APIRouter(prefix="/calendar", tags=["Calendário ICS"])
settings = get_settings()


def gerar_token_calendario(user_id: str) -> str:
    """HMAC determinístico — sem estado no banco."""
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"ics:{user_id}".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def _ics_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;") \
                    .replace(",", "\\,").replace("\n", "\\n")


@router.get("/{user_id}/{token}.ics")
async def feed_ics(user_id: str, token: str):
    if not hmac.compare_digest(token, gerar_token_calendario(user_id)):
        raise HTTPException(status_code=403, detail="Token inválido")

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(
            User.id == user_id, User.is_active == True
        ))).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404)

        # Próximos 120 dias: audiências (todas) + prazos alta/crítica
        hoje = datetime.utcnow().date()
        rows = (await db.execute(
            select(Deadline).where(
                Deadline.responsavel_id == user_id,
                Deadline.deleted_at.is_(None),
                Deadline.status == "pendente",
                Deadline.data_prazo >= hoje,
                Deadline.data_prazo <= hoje + timedelta(days=120),
            )
        )).scalars().all()

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
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}\r\n"
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
        + "".join(eventos) +
        "END:VCALENDAR\r\n"
    )
    return Response(content=ics, media_type="text/calendar; charset=utf-8")
