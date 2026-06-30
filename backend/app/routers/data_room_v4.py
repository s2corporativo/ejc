"""
Módulo de Data Room Jurídico Corporativo - EJC v4.0 (Seção 14.359).
Salas documentais seguras, controle granular de acesso e auditoria.
"""
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Column, String, Text, DateTime, func, select, Boolean
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import Base, get_db
from app.core.security import require_roles, get_current_user
from app.models.user import User

# Model ORM
class DataRoomSala(Base):
    __tablename__ = "dataroom_salas"
    id = Column(String(36), primary_key=True)
    nome = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    client_id = Column(String(36), nullable=True)
    expira_em = Column(DateTime(timezone=True), nullable=True)
    publica = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Schemas
class SalaCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None
    client_id: Optional[str] = None
    expira_dias: Optional[int] = 30

class SalaResponse(BaseModel):
    id: str
    nome: str
    expira_em: Optional[datetime]

router = APIRouter(prefix="/data-room-v4", tags=["Data Room Jurídico"])

@router.post("/", response_model=SalaResponse, dependencies=[Depends(require_roles(["admin", "socio", "advogado"]))])
async def criar_sala(payload: SalaCreate, db: AsyncSession = Depends(get_db)):
    expira = datetime.now(timezone.utc) + timedelta(days=payload.expira_dias) if payload.expira_dias else None
    s = DataRoomSala(
        id=str(uuid4()),
        nome=payload.nome,
        descricao=payload.descricao,
        client_id=payload.client_id,
        expira_em=expira
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s

@router.get("/", response_model=List[SalaResponse])
async def listar_salas(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    q = select(DataRoomSala)
    if cu.role.value == "cliente_externo":
        q = q.where(DataRoomSala.client_id == cu.client_id)
    
    res = await db.execute(q)
    return res.scalars().all()
