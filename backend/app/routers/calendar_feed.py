# Feed ICS por advogado: audiências e prazos críticos no calendário pessoal.
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.rate_limit import consumir
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.calendar_feed_credential import CalendarFeedCredential
from app.models.deadline import Deadline
from app.models.user import User
from app.services.security_service import obter_ip_real

router = APIRouter(prefix="/calendar", tags=["Calendário ICS"])
settings = get_settings()


def gerar_token_calendario(user_id: str, version: int = 1) -> str:
    """Gera token HMAC compatível com links legados e revogável por versão.

    A versão 1 preserva exatamente o formato anterior para não invalidar links
    existentes. A primeira rotação avança para v2 e revoga o token legado.
    """
    mensagem = f"ics:{user_id}" if version == 1 else f"ics:{user_id}:v{version}"
    return hmac.new(
        settings.SECRET_KEY.encode(),
        mensagem.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def _url_calendario(user_id: str, version: int) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    token = gerar_token_calendario(user_id, version)
    return f"{base}/api/calendar/{user_id}/{token}.ics"


async def _versao_feed(db: AsyncSession, user_id: str) -> int:
    version = (
        await db.execute(
            select(CalendarFeedCredential.version).where(
                CalendarFeedCredential.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    return int(version or 1)


async def obter_url_calendario(
    db: AsyncSession,
    user_id: str,
) -> dict[str, object]:
    """Fonte única da URL vigente, reutilizada pela rota canônica e legado."""
    version = await _versao_feed(db, user_id)
    return {
        "url": _url_calendario(user_id, version),
        "version": version,
        "revogavel": True,
    }


def _ics_escape(value: str) -> str:
    return (
        (value or "")
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
async def minha_url_calendario_revogavel(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Retorna o link vigente sem expor a chave usada para assiná-lo."""
    return await obter_url_calendario(db, cu.id)


@router.post("/me/rotate")
async def rotacionar_url_calendario(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Revoga imediatamente o link anterior e emite uma nova versão."""
    agora = datetime.now(timezone.utc)
    stmt = (
        pg_insert(CalendarFeedCredential)
        .values(
            user_id=cu.id,
            version=2,
            rotated_at=agora,
        )
        .on_conflict_do_update(
            index_elements=[CalendarFeedCredential.user_id],
            set_={
                "version": CalendarFeedCredential.version + 1,
                "rotated_at": agora,
            },
        )
        .returning(CalendarFeedCredential.version)
    )
    version = int((await db.execute(stmt)).scalar_one())
    role = str(getattr(cu.role, "value", cu.role))
    await criar_audit_log(
        db,
        cu.id,
        role,
        "ROTATE_ICS",
        "calendar_feed",
        cu.id,
        detalhes=f"version={version}",
        ip=obter_ip_real(request),
    )
    await db.commit()
    return {
        "url": _url_calendario(cu.id, version),
        "version": version,
        "revogado": True,
    }


@router.get(
    "/{user_id}/{token}.ics",
    dependencies=[Depends(_rl_feed_ics)],
)
async def feed_ics(user_id: str, token: str):
    async with AsyncSessionLocal() as db:
        version = await _versao_feed(db, user_id)
        esperado = gerar_token_calendario(user_id, version)
        if not hmac.compare_digest(token, esperado):
            raise HTTPException(status_code=403, detail="Token inválido ou revogado")

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
    for deadline in rows:
        tipo = getattr(deadline.tipo, "value", str(deadline.tipo))
        eh_audiencia = tipo == "audiencia"
        prioridade = getattr(
            deadline.prioridade,
            "value",
            str(deadline.prioridade),
        )
        if not eh_audiencia and prioridade not in ("alta", "critica"):
            continue
        data = deadline.data_prazo.strftime("%Y%m%d")
        emoji = "⚖️" if eh_audiencia else "⏰"
        eventos.append(
            "BEGIN:VEVENT\r\n"
            f"UID:ejc-{deadline.id}@depaulateixeira\r\n"
            f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"DTSTART;VALUE=DATE:{data}\r\n"
            f"SUMMARY:{emoji} {_ics_escape(deadline.titulo)}\r\n"
            "DESCRIPTION:"
            f"{_ics_escape(deadline.base_legal or deadline.descricao or 'EJC')}\r\n"
            "BEGIN:VALARM\r\n"
            "TRIGGER:-P1D\r\n"
            "ACTION:DISPLAY\r\n"
            "DESCRIPTION:Prazo amanhã\r\n"
            "END:VALARM\r\n"
            "END:VEVENT\r\n"
        )

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
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
