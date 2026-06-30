# -- app/models/dossie_estrategico.py --
from __future__ import annotations
import enum
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Enum as SAEnum, func
from app.core.database import Base

class DossieStatus(str, enum.Enum):
    rascunho  = "rascunho"
    aprovado  = "aprovado"
    arquivado = "arquivado"

class DossieEstrategico(Base):
    __tablename__ = "dossies_estrategicos"
    id            = Column(String(36), primary_key=True)
    case_id       = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    versao        = Column(Integer, nullable=False, default=1)
    titulo        = Column(String(300))
    conteudo_texto = Column(Text)
    conteudo_html  = Column(Text)
    secoes_json    = Column(Text)
    status      = Column(SAEnum(DossieStatus, name="dossiestrategicostatus"), nullable=False, default=DossieStatus.rascunho)
    modelo_ia      = Column(String(100))
    provedor_ia    = Column(String(30))
    tokens_usados  = Column(Integer)
    gerado_por   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    aprovado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    aprovado_em  = Column(DateTime(timezone=True), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
