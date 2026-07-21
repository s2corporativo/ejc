"""
Módulo legado de Data Room Jurídico Corporativo (v4).

Mantido temporariamente por compatibilidade enquanto os dados são consolidados
em /api/data-rooms. A superfície legado recebe os mesmos controles de carteira
do domínio canônico e não pode ser usada para contornar ownership.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Column, DateTime, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, get_db
from app.core.ownership import is_gestao
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.client import Client
from app.models.user import User


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
    nome: str = Field(min_length=3, max_length=255)
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
    tags=["Data Room Jurídico — legado"],
)


def _pode_editar(cu: User) -> bool:
    return ROLE_LEVEL.get(cu.role.value, 0) >= ROLE_LEVEL["advogado"]


def _ids_clientes_visiveis(cu: User):
    """Reusa a regra canônica de carteira sem duplicar a política."""
    from app.routers.data_room import _ids_clientes_visiveis as _canonico

    return _canonico(cu)


async def _validar_cliente_v4(
    db: AsyncSession,
    cu: User,
    client_id: str | None,
) -> None:
    """Impede criação de sala legado para cliente de outra carteira."""
    if is_gestao(cu):
        return
    if not client_id:
        raise HTTPException(
            422,
            "Na rota legado, informe um cliente da sua carteira",
        )

    from app.routers.clients import _pode_ver_cliente

    cli = (
        await db.execute(
            select(Client).where(
                Client.id == client_id,
                Client.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if cli is None or not await _pode_ver_cliente(cu, cli, db):
        raise HTTPException(404, "Cliente não encontrado")


@router.post(
    "/",
    response_model=SalaResponse,
    deprecated=True,
)
async def criar_sala(
    payload: SalaCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403, "Sem permissão para criar data rooms")

    await _validar_cliente_v4(db, cu, payload.client_id)
    expira = (
        datetime.now(timezone.utc) + timedelta(days=payload.expira_dias)
        if payload.expira_dias
        else None
    )
    sala = DataRoomSala(
        id=str(uuid4()),
        nome=payload.nome,
        descricao=payload.descricao,
        client_id=payload.client_id,
        expira_em=expira,
    )
    db.add(sala)
    await db.commit()
    await db.refresh(sala)

    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/data-rooms>; rel="successor-version"'
    return sala


@router.get(
    "/",
    response_model=List[SalaResponse],
    deprecated=True,
)
async def listar_salas(
    response: Response,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403, "Sem permissão para listar data rooms")

    q = select(DataRoomSala)
    if not is_gestao(cu):
        q = q.where(
            DataRoomSala.client_id.is_not(None),
            DataRoomSala.client_id.in_(_ids_clientes_visiveis(cu)),
        )
    q = q.order_by(DataRoomSala.created_at.desc())

    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/data-rooms>; rel="successor-version"'
    res = await db.execute(q)
    return res.scalars().all()
