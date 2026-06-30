# ── app/models/wiki.py ───────────────────────────────────────────────────────
# Wiki interna do escritório (#93): procedimentos, tabela de honorários, contatos.
from __future__ import annotations
from sqlalchemy import Column, String, Text, DateTime, func
from app.core.database import Base


class WikiPagina(Base):
    __tablename__ = "wiki_paginas"

    id        = Column(String(36), primary_key=True)
    titulo    = Column(String(255), nullable=False)
    slug      = Column(String(255), nullable=True)
    categoria = Column(String(60), nullable=True, index=True)
    conteudo  = Column(Text, nullable=True)
    atualizado_por = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
