"""Compatibilidade do antigo Data Room v4.

A URL `/data-room-v4` permanece durante a migração, porém novas leituras e
escritas usam exclusivamente `data_rooms`. `dataroom_salas` fica somente como
origem histórica até o expurgo posterior à telemetria.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Column, DateTime, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, get_db
from app.core.security import ROLE_LEVEL, get_current_user, require_roles
from app.models.client import Client
from app.models.data_room import DataRoom
from app.models.user import User


# Mantido no metadata até a etapa final de exclusão física da tabela legada.
# Nenhum endpoint abaixo cria, atualiza ou remove registros nesta classe.
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
    nome: str = Field(min_length=1, max_length=255)
    descricao: Optional[str] = None
    client_id: Optional[str] = None
    expira_dias: Optional[int] = Field(default=30, ge=1, le=3650)


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


def _compat(room: DataRoom) -> dict:
    return {
        "id": room.id,
        "nome": room.nome,
        "expira_em": room.legacy_expira_em,
    }


@router.post("/", response_model=SalaResponse, status_code=201, deprecated=True)
async def criar_sala(
    payload: SalaCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["admin", "socio", "advogado"])),
):
    # A tabela canônica possui FK; converter uma referência inexistente em 500
    # seria pior que o legado. Recusa de forma explícita e auditável pelo HTTP.
    if payload.client_id:
        client_exists = (
            await db.execute(
                select(Client.id).where(
                    Client.id == payload.client_id,
                    Client.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if client_exists is None:
            raise HTTPException(422, "Cliente informado não existe ou está excluído")

    expira_em = (
        datetime.now(timezone.utc) + timedelta(days=payload.expira_dias)
        if payload.expira_dias
        else None
    )
    room = DataRoom(
        id=str(uuid4()),
        nome=payload.nome,
        descricao=payload.descricao,
        client_id=payload.client_id,
        created_by=cu.id,
        legacy_expira_em=expira_em,
        # O v4 não expunha este campo na criação; nunca abra acesso implícito.
        legacy_publica=False,
    )
    db.add(room)
    await db.commit()
    await db.refresh(room)
    _headers(response)
    return _compat(room)


@router.get("/", response_model=list[SalaResponse], deprecated=True)
async def listar_salas(
    response: Response,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    role = cu.role.value
    query = select(DataRoom).where(DataRoom.deleted_at.is_(None))
    if role == "cliente_externo":
        query = query.where(DataRoom.client_id == cu.client_id)
    elif ROLE_LEVEL.get(role, 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(403, "Sem permissão para listar data rooms")

    rooms = (
        await db.execute(query.order_by(DataRoom.created_at.desc()))
    ).scalars().all()
    _headers(response)
    return [_compat(room) for room in rooms]
