# ── app/models/case_parte.py ─────────────────────────────────────────────────
# Parte processual de um caso (autor, réu, terceiro, advogado, procurador).
# Model ORM para a tabela `case_partes` que JÁ EXISTE (antes manipulada por SQL
# cru). Mapeia exatamente as colunas reais; não cria/altera schema.
from __future__ import annotations
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class CaseParte(Base):
    __tablename__ = "case_partes"

    id      = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    tipo    = Column(String(30), nullable=False)   # autor|reu|terceiro|advogado|procurador
    papel_processual    = Column(String(100), nullable=True)
    nome    = Column(String(255), nullable=False)
    cpf_cnpj = Column(String(18), nullable=True)
    qualificacao = Column(Text, nullable=True)
    email   = Column(String(255), nullable=True)
    telefone = Column(String(20), nullable=True)
    representante_legal = Column(String(255), nullable=True)
    oab     = Column(String(20), nullable=True)
    client_id = Column(String, ForeignKey("clients.id", ondelete="SET NULL"),
                       nullable=True)
    ativo   = Column(Boolean, default=True)
    observacoes = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(),
                         onupdate=func.now())
    created_by  = Column(String, nullable=True)

    case = relationship("Case", back_populates="partes")
