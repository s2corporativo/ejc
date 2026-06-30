"""
Módulo de Banco de Teses Jurídicas Estruturado - EJC v4.0 (Seção 3.122).
Cadastro, ranking de desempenho e reaproveitamento inteligente de teses.
"""
from uuid import uuid4
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Column, String, Text, Float, DateTime, func, select, Boolean
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.models.user import User

# Model ORM
class TeseJuridica(Base):
    __tablename__ = "teses_juridicas_v4"
    id = Column(String(36), primary_key=True)
    titulo = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=False)
    fundamentacao = Column(Text, nullable=False)
    jurisprudencia = Column(Text, nullable=True)
    taxa_sucesso = Column(Float, default=0.0)
    area_juridica = Column(String(50), nullable=False)
    tribunal = Column(String(100), nullable=True)
    magistrado = Column(String(100), nullable=True)
    vencedora = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Schemas
class TeseCreate(BaseModel):
    titulo: str
    descricao: str
    fundamentacao: str
    jurisprudencia: Optional[str] = None
    area_juridica: str
    tribunal: Optional[str] = None
    magistrado: Optional[str] = None

class TeseResponse(TeseCreate):
    id: str
    taxa_sucesso: float
    vencedora: bool

router = APIRouter(prefix="/teses-v4", tags=["Banco de Teses Jurídicas"])

@router.post("/", response_model=TeseResponse)
async def criar_tese(payload: TeseCreate, db: AsyncSession = Depends(get_db)):
    t = TeseJuridica(id=str(uuid4()), **payload.model_dump())
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t

@router.get("/", response_model=List[TeseResponse])
async def listar_teses(
    area: Optional[str] = None, 
    vencedoras: bool = False,
    db: AsyncSession = Depends(get_db)
):
    q = select(TeseJuridica)
    if area:
        q = q.where(TeseJuridica.area_juridica == area)
    if vencedoras:
        q = q.where(TeseJuridica.vencedora == True)
    
    q = q.order_by(TeseJuridica.taxa_sucesso.desc())
    res = await db.execute(q)
    return res.scalars().all()

@router.get("/sugestao-ia")
async def sugerir_teses_ia(contexto: str, db: AsyncSession = Depends(get_db)):
    """Sugestão de teses pela IA integrada ao RAG (Seção 3.136)."""
    from app.core.ai_brain import ai_gateway
    # Busca teses similares no banco via RAG (simulado aqui)
    teses_existentes = await listar_teses(db=db)
    contexto_teses = "\n".join([f"- {t.titulo}: {t.descricao}" for t in teses_existentes[:5]])
    
    prompt = f"Com base no contexto do caso: {contexto}\n\nE nestas teses do escritório:\n{contexto_teses}\n\nSugira a melhor estratégia e novas teses."
    return await ai_gateway.processar_demanda(prompt, tipo="juridico_profundo")
