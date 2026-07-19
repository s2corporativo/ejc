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
        Index(
            "ix_atendimentos_solicitacao_sla",
            "solicitacao_atendida",
            "solicitacao_prazo",
        ),
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
    solicitacao_prazo      = Column(DateTime(timezone=True), nullable=True)
    solicitacao_prioridade = Column(String(10), nullable=False, default="normal",
                                    server_default="normal")
    solicitacao_responsavel_id = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    solicitacao_alerta_nivel = Column(String(20), nullable=True)
    task_id                = Column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True, unique=True, index=True,
    )

    # Resultado do canal de contato. Ações rápidas começam como "iniciado" e
    # só viram "confirmado" após validação humana na linha do tempo.
    contato_status         = Column(String(20), nullable=False, default="confirmado",
                                    server_default="confirmado")

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
