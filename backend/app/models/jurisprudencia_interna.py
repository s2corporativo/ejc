# ── app/models/jurisprudencia_interna.py ─────────────────────────────────────
# Repositório interno de jurisprudência — julgados salvos, classificados e rankeados.
from __future__ import annotations
import enum

from sqlalchemy import (
    Column, String, Text, Integer, Boolean,
    Date, DateTime, ForeignKey, Enum as SAEnum, func,
)
from app.core.database import Base


class JuriResultado(str, enum.Enum):
    favoravel    = "favoravel"
    desfavoravel = "desfavoravel"
    neutro       = "neutro"
    acordo       = "acordo"


class JurisprudenciaInterna(Base):
    __tablename__ = "jurisprudencias_internas"

    id                = Column(String(36), primary_key=True)
    titulo            = Column(String(300), nullable=False)
    ementa            = Column(Text, nullable=False)
    fundamentacao     = Column(Text)

    # Identificação do julgado
    tribunal          = Column(String(120))
    relator           = Column(String(200))
    numero_acordao    = Column(String(100))
    data_julgamento   = Column(Date)
    fonte             = Column(String(50))    # stj|stf|tjmg|tjsp|trf|datajud|manual
    link_original     = Column(Text)

    # Classificação
    area_juridica     = Column(String(60))
    tags              = Column(Text)
    resultado         = Column(SAEnum(JuriResultado, name="juriresultado"), nullable=True)
    favorito          = Column(Boolean, nullable=False, default=False)

    # Métricas de uso
    vezes_citada      = Column(Integer, nullable=False, default=0)
    classificacao_ia  = Column(Text)   # JSON: {"area": ..., "temas": [...], "palavras_chave": [...]}

    created_by        = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at        = Column(DateTime(timezone=True), nullable=True)
