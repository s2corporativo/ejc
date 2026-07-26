# ── app/models/data_room.py ───────────────────────────────────────────────────
# Data Room — salas de documentos com acesso controlado e links com expiração.
from __future__ import annotations

from sqlalchemy import (
    Column, String, Text, Integer, Boolean,
    DateTime, ForeignKey, func,
)
from app.core.database import Base


class DataRoom(Base):
    __tablename__ = "data_rooms"

    id          = Column(String(36), primary_key=True)
    nome        = Column(String(200), nullable=False)
    descricao   = Column(Text)
    # index=True declara ix_data_rooms_case_id / ix_data_rooms_client_id (076, #11)
    case_id     = Column(String(36), ForeignKey("cases.id",   ondelete="SET NULL"), nullable=True, index=True)
    client_id   = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by  = Column(String(36), ForeignKey("users.id",   ondelete="SET NULL"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at  = Column(DateTime(timezone=True), nullable=True)


class DataRoomArquivo(Base):
    __tablename__ = "data_room_arquivos"

    id               = Column(String(36), primary_key=True)
    data_room_id     = Column(String(36), ForeignKey("data_rooms.id", ondelete="CASCADE"),
                               nullable=False)
    document_id      = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"),
                               nullable=False)
    nome_exibicao    = Column(String(300))   # pode diferir do nome original
    adicionado_por   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    added_at         = Column(DateTime(timezone=True), server_default=func.now())


class DataRoomLink(Base):
    """Link público com expiração para acesso externo (cliente, perito, etc.)."""
    __tablename__ = "data_room_links"

    id                = Column(String(36), primary_key=True)
    data_room_id      = Column(String(36), ForeignKey("data_rooms.id", ondelete="CASCADE"),
                                nullable=False)
    token             = Column(String(64), unique=True, nullable=False)    # SHA-256 hex do segredo (nunca em claro)
    descricao         = Column(String(200))    # para quem / para que foi gerado
    expira_em         = Column(DateTime(timezone=True))
    max_acessos       = Column(Integer)         # None = ilimitado
    acessos_realizados = Column(Integer, nullable=False, default=0)
    senha_hash        = Column(String(128))     # bcrypt (opcional)
    ativo             = Column(Boolean, nullable=False, default=True)
    criado_por        = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())


class DataRoomAcessoLog(Base):
    """Registro de cada acesso ao Data Room via link externo."""
    __tablename__ = "data_room_acesso_logs"

    id              = Column(String(36), primary_key=True)
    link_id         = Column(String(36), ForeignKey("data_room_links.id", ondelete="CASCADE"),
                              nullable=False)
    ip              = Column(String(45))
    user_agent      = Column(Text)
    acessado_em     = Column(DateTime(timezone=True), server_default=func.now())
