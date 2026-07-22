"""Compatibilidade temporária do antigo Data Room v4.

A URL `/data-room-v4` permanece para favoritos e integrações históricas, mas
toda nova leitura e escrita é executada pelo domínio canônico `data_rooms`.
A tabela `dataroom_salas` fica somente como origem histórica do backfill da
migration 114, sem receber novas gravações.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Column, DateTime, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.models.user import User


# Mantido no metadata até exclusão física posterior a telemetria e homologação.
class DataRoomSala(Base):
    __tablename__ = "dataroom_salas"

    id = Column(String(36), primary_key=True)
    nome = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    client_id = Column(String(36), nullable=True)
    expira_em = Column(DateTime(timezone=True), nullable=True)
    publica = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SalaCreate(BaseModel):
    nome: str = Field(min_length=3, max_length=200)
    descricao: Optional[str] = Field(default=None, max_length=4000)
    client_id: Optional[str] = None
    expira_dias: Optional[int] = Field(default=30, ge=1, le=365)


class SalaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nome: str
    expira_em: Optional[datetime]


router = APIRouter(
    prefix="/data-room-v4",
    tags=["Data Room Jurídico — compatibilidade"],
    deprecated=True,
)


def _headers_deprecacao(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/data-rooms>; rel="successor-version"'


def _compat(room: dict) -> dict:
    return {
        "id": room["id"],
        "nome": room["nome"],
        # A expiração agora pertence ao link externo, não à sala canônica.
        "expira_em": None,
    }


@router.post(
    "/",
    response_model=SalaResponse,
    status_code=201,
    deprecated=True,
)
async def criar_sala(
    payload: SalaCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Cria a sala no domínio canônico, sem dupla escrita na tabela v4."""
    from app.routers.data_room import DataRoomIn, criar_data_room

    descricao = payload.descricao
    if payload.expira_dias:
        aviso = (
            f"Prazo solicitado na API v4: {payload.expira_dias} dia(s). "
            "No domínio canônico, a expiração é definida no link externo."
        )
        descricao = f"{descricao}\n{aviso}" if descricao else aviso

    room = await criar_data_room(
        DataRoomIn(
            nome=payload.nome,
            descricao=descricao,
            client_id=payload.client_id,
        ),
        db=db,
        cu=cu,
    )
    _headers_deprecacao(response)
    return _compat(room)


@router.get(
    "/",
    response_model=list[SalaResponse],
    deprecated=True,
)
async def listar_salas(
    response: Response,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista somente salas canônicas visíveis pelas regras centrais de carteira."""
    from app.routers.data_room import listar_data_rooms

    page = await listar_data_rooms(
        case_id=None,
        client_id=None,
        page=1,
        per_page=50,
        db=db,
        cu=cu,
    )
    _headers_deprecacao(response)
    return [_compat(room) for room in page["items"]]
