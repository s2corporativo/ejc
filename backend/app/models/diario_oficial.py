# ── app/models/diario_oficial.py ─────────────────────────────────────────────
# Monitor de Diários Oficiais — DOU, DOE, DOM.
from __future__ import annotations

from sqlalchemy import (
    Column, String, Text, Boolean,
    Date, DateTime, ForeignKey, func,
)
from app.core.database import Base


class DiarioOficialKeyword(Base):
    """Palavras-chave para monitorar no Diário Oficial."""
    __tablename__ = "diario_oficial_keywords"

    id           = Column(String(36), primary_key=True)
    keyword      = Column(String(200), nullable=False)
    fonte        = Column(String(20), nullable=False, default="dou")  # dou|doe_mg|dom
    ativo        = Column(Boolean, nullable=False, default=True)
    case_id      = Column(String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    created_by   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())


class DiarioOficialAlerta(Base):
    """Publicação encontrada no Diário Oficial que casou com uma keyword."""
    __tablename__ = "diario_oficial_alertas"

    id               = Column(String(36), primary_key=True)
    fonte            = Column(String(20), nullable=False)  # dou|doe_mg|dom
    edicao           = Column(String(30))
    data_publicacao  = Column(Date)
    secao            = Column(String(10))   # 1|2|3|extra
    titulo           = Column(String(500))
    resumo           = Column(Text)
    link             = Column(Text)
    keyword_match    = Column(String(200))  # qual keyword disparou
    keyword_id       = Column(String(36), ForeignKey("diario_oficial_keywords.id",
                              ondelete="SET NULL"), nullable=True)
    lido             = Column(Boolean, nullable=False, default=False)
    case_id          = Column(String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
