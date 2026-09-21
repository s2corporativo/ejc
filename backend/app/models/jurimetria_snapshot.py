"""Snapshot agregado da jurimetria externa.

Persiste SOMENTE o resultado agregado já minimizado. Não armazena número CNJ,
partes, relator, decisão integral ou payload bruto do DataJud.
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class JurimetriaSnapshot(Base):
    __tablename__ = "jurimetria_snapshots"
    __table_args__ = (
        Index("ix_jurimetria_snapshots_tribunal_coleta", "tribunal", "coletado_em"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    snapshot_key = Column(String(64), nullable=False, unique=True, index=True)
    fonte = Column(String(160), nullable=False)
    tribunal = Column(String(20), nullable=False)
    filtros = Column(JSONB, nullable=False, default=dict)
    agregado = Column(JSONB, nullable=False)
    tpu_versao = Column(String(40), nullable=True)
    n_documentos = Column(Integer, nullable=False, default=0)
    amostra_truncada = Column(Boolean, nullable=False, default=False)
    coletado_em = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
