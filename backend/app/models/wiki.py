# ── app/models/wiki.py ───────────────────────────────────────────────────────
# Wiki interna do escritório (#93): procedimentos, tabela de honorários, contatos.
#
# LEGADO SEM SUPERFÍCIE (pente fino 2026-07): o router da Wiki foi removido na
# onda 1 e a tela /wiki foi unificada na aba Conhecimento de /inteligencia —
# a tabela `wiki_paginas` não tem mais leitura/escrita pela aplicação. O model
# é MANTIDO de propósito: sem ele, o autogenerate do Alembic sugeriria um
# drop_table espúrio (ver guarda include_name() em alembic/env.py). A remoção
# definitiva aguarda decisão de migração destrutiva com backup prévio
# (scripts/backup.sh) e migration explícita — não remover este arquivo antes.
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
