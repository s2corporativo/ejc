# ── app/models/task.py ───────────────────────────────────────────────────────
from sqlalchemy import Column, String, Text, Date, DateTime, Enum as SAEnum, func, ForeignKey
from app.core.database import Base
import enum


class TaskStatus(str, enum.Enum):
    a_fazer   = "a_fazer"
    fazendo   = "fazendo"
    concluida = "concluida"


class Task(Base):
    __tablename__ = "tasks"

    id             = Column(String(36), primary_key=True)
    titulo         = Column(String(255), nullable=False)
    descricao      = Column(Text)
    status         = Column(SAEnum(TaskStatus), nullable=False, default=TaskStatus.a_fazer, index=True)
    prioridade     = Column(String(10), default="media")
    data_limite    = Column(Date, nullable=True)
    case_id        = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    responsavel_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    criado_por     = Column(String(36), nullable=True)
    concluida_em   = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
