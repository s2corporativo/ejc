# ── app/models/atendimento.py ──────────────────────────────────────────────────
# Histórico de atendimentos ao cliente — reuniões, ligações, e-mails, etc.
from __future__ import annotations
import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from app.core.database import Base


class AtendimentoTipo(str, enum.Enum):
    reuniao_presencial = "reuniao_presencial"
    reuniao_virtual    = "reuniao_virtual"
    ligacao            = "ligacao"
    email              = "email"
    whatsapp           = "whatsapp"
    protocolo          = "protocolo"
    visita             = "visita"
    outros             = "outros"


class Atendimento(Base):
    __tablename__ = "atendimentos"
    __table_args__ = (
        Index("ix_atendimentos_client_data", "client_id", "data_atendimento"),
    )

    id                   = Column(String(36), primary_key=True)
    client_id            = Column(String(36), ForeignKey("clients.id", ondelete="CASCADE"),
                                  nullable=False)
    case_id              = Column(String(36), ForeignKey("cases.id", ondelete="SET NULL"),
                                  nullable=True)

    tipo                 = Column(SAEnum(AtendimentoTipo, name="atendimentotipo"),
                                  nullable=False)
    data_atendimento     = Column(DateTime(timezone=True), nullable=False)
    duracao_min          = Column(String(10))           # duração em minutos (livre)
    resumo               = Column(Text, nullable=False) # recado / o que foi tratado
    proximo_passo        = Column(Text)                 # ação acordada / follow-up

    # Solicitação trazida no atendimento e seu acompanhamento na linha do tempo.
    solicitacao           = Column(Text, nullable=True)
    solicitacao_atendida  = Column(Boolean, nullable=False, default=False,
                                   server_default="false")
    atendida_em           = Column(DateTime(timezone=True), nullable=True)
    atendida_por_id       = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"),
                                   nullable=True)

    observacoes_privadas     = Column(Text)     # notas internas (não vai ao portal do cliente)

    # Advogado que realizou o atendimento (pode diferir de quem registrou)
    advogado_responsavel_id  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"),
                                       nullable=True)
    duracao_horas            = Column(Numeric(5, 2))   # 1.5 = 1h30
    satisfacao_cliente       = Column(Integer)          # 1-5

    created_by           = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"),
                                  nullable=True)
    created_at           = Column(DateTime(timezone=True), server_default=func.now())
    updated_at           = Column(DateTime(timezone=True), server_default=func.now(),
                                  onupdate=func.now())
