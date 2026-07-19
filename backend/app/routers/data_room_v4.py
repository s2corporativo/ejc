"""Compatibilidade do antigo Data Room v4.

A URL `/data-room-v4` permanece durante a migração, porém novas leituras e
escritas usam a tabela canônica `data_rooms`. A tabela `dataroom_salas` fica
somente como origem histórica até expurgo posterior à telemetria.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.models.data_room import DataRoom
from app.models.user import User

# Mantido no metadata até a etapa final de exclusão física da tabela legada.
from sqlalchemy import Boolean, Column, DateTime, String, Text, func


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
    nome: str
    descricao: Optional[str] = None
    client_id: Optional[str] = None
    expira_dias: Optional[int] = 30


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


def _headers(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/v1/data-rooms>; rel="successor-version"'


def _compat(room: dict | DataRoom) -> dict:
    if isinstance(room, dict):
        return {"id": room["id"], "nome": room["nome"], "expira_em": None}
    return {"id": room.id, "nome": room.nome, "expira_em": None}


@router.post("/", response_model=SalaResponse, status_code=201, deprecated=True)
async def criar_sala(
    payload: SalaCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    from app.routers.data_room import DataRoomIn, criar_data_room

    descricao = payload.descricao
    if payload.expira_dias:
        aviso = (
            f"Prazo solicitado na API v4: {payload.expira_dias} dia(s). "
            "Para acesso externo, gere um link canônico com expiração."
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
    _headers(response)
    return _compat(room)


@router.get("/", response_model=list[SalaResponse], deprecated=True)
async def listar_salas(
    response: Response,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    role = cu.role.value
    if role == "cliente_externo":
        rows = (
            await db.execute(
                select(DataRoom)
                .where(
                    DataRoom.client_id == cu.client_id,
                    DataRoom.deleted_at.is_(None),
                )
                .order_by(DataRoom.created_at.desc())
            )
        ).scalars().all()
        result = [_compat(room) for room in rows]
    else:
        from app.routers.data_room import listar_data_rooms

        page = await listar_data_rooms(
            case_id=None,
            client_id=None,
            page=1,
            per_page=50,
            db=db,
            cu=cu,
        )
        result = [_compat(room) for room in page["items"]]
    _headers(response)
    return result
