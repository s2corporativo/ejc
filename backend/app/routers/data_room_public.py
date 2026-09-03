"""Superfície pública token-bound do Data Room.

Não reutiliza nem afrouxa os downloads autenticados de ``/documents``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import consumir
from app.services.data_room_public import (
    abrir_manifesto,
    headers_publicos,
    preparar_download,
)
from app.services.security_service import obter_ip_real

router = APIRouter(prefix="/data-rooms", tags=["Data Room Público"])


async def _rl_manifesto(request: Request) -> None:
    await consumir(
        "data_room_public_manifest",
        f"ip:{obter_ip_real(request)}",
        30,
    )


async def _rl_download(request: Request) -> None:
    await consumir(
        "data_room_public_download",
        f"ip:{obter_ip_real(request)}",
        120,
    )


@router.get(
    "/acesso/{token}/manifesto",
    include_in_schema=False,
    dependencies=[Depends(_rl_manifesto)],
)
async def manifesto_publico(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return await abrir_manifesto(db, token, request)


@router.get(
    "/acesso/{token}/arquivos/{arquivo_id}",
    include_in_schema=False,
    dependencies=[Depends(_rl_download)],
)
async def download_publico(
    token: str,
    arquivo_id: str,
    request: Request,
    n: int = Query(..., ge=1),
    exp: int = Query(..., ge=1),
    grant: str = Query(..., min_length=64, max_length=64),
    db: AsyncSession = Depends(get_db),
):
    entrega = await preparar_download(
        db,
        token,
        arquivo_id,
        acesso_numero=n,
        exp=exp,
        grant=grant,
        request=request,
    )
    headers = headers_publicos(entrega.filename)
    if entrega.content is not None:
        return Response(
            content=entrega.content,
            media_type=entrega.media_type,
            headers=headers,
        )
    return FileResponse(
        entrega.local_path,
        media_type=entrega.media_type,
        headers=headers,
    )
