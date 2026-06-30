# ── app/models/deadline.py ───────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Date, Enum as SAEnum, func, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class DeadlineTipo(str, enum.Enum):
    processual     = "processual"      # prazo judicial
    administrativo = "administrativo"  # ex: defesa IBAMA
    interno        = "interno"         # tarefa do escritório
    audiencia      = "audiencia"
    prescricao     = "prescricao"


class DeadlineStatus(str, enum.Enum):
    pendente  = "pendente"
    concluido = "concluido"
    vencido   = "vencido"
    cancelado = "cancelado"


class DeadlinePrioridade(str, enum.Enum):
    baixa   = "baixa"
    media   = "media"
    alta    = "alta"
    critica = "critica"


class Deadline(Base):
    __tablename__ = "deadlines"

    id        = Column(String(36), primary_key=True)
    titulo    = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    tipo      = Column(SAEnum(DeadlineTipo), nullable=False, default=DeadlineTipo.processual)
    prioridade = Column(SAEnum(DeadlinePrioridade), nullable=False, default=DeadlinePrioridade.media)
    status    = Column(SAEnum(DeadlineStatus), nullable=False, default=DeadlineStatus.pendente, index=True)

    data_prazo     = Column(Date, nullable=False, index=True)   # data fatal
    data_intimacao = Column(Date, nullable=True)
    data_conclusao = Column(DateTime(timezone=True), nullable=True)
    base_legal     = Column(String(255), nullable=True)         # ex: "CPC art. 335"

    # Confirmação de ciência (audit LGPD)
    ciencia_confirmada    = Column(Boolean, default=False)
    ciencia_confirmada_em = Column(DateTime(timezone=True), nullable=True)
    ciencia_confirmada_por = Column(String(36), nullable=True)

    # Alertas enviados (evita duplicação)
    alerta_7d_enviado = Column(Boolean, default=False)
    alerta_3d_enviado = Column(Boolean, default=False)
    alerta_1d_enviado = Column(Boolean, default=False)

    case_id        = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    responsavel_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    observacoes    = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case        = relationship("Case", back_populates="deadlines")
    responsavel = relationship("User", foreign_keys=[responsavel_id], back_populates="deadlines")
