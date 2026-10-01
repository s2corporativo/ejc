from __future__ import annotations

import enum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import validates

from app.core.database import Base
from app.models.ai_log import pseudonimizar_texto_auditoria


class AILearningEventType(str, enum.Enum):
    correction = "correction"
    error = "error"
    outcome = "outcome"
    benchmark = "benchmark"


class AILearningEvent(Base):
    """Feedback jurídico supervisionado para evolução do EJC.

    Nenhuma linha vira "verdade jurídica" por existir. O evento nasce não
    aprovado; somente revisão humana explícita pode marcá-lo como apto a
    benchmark/aprendizado institucional. Texto é pseudonimizado na própria
    barreira ORM, como AILog.
    """

    __tablename__ = "ai_learning_events"
    __table_args__ = (
        Index("ix_ai_learning_events_type_area_created", "event_type", "area", "created_at"),
        Index("ix_ai_learning_events_approved_created", "approved", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ai_log_id = Column(
        String(36), ForeignKey("ai_logs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    case_id = Column(
        String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    event_type = Column(SAEnum(AILearningEventType), nullable=False, index=True)
    area = Column(String(80), nullable=True, index=True)
    difficulty = Column(String(20), nullable=True, index=True)
    error_type = Column(String(80), nullable=True, index=True)
    severity = Column(String(20), nullable=True, index=True)

    original_text = Column(Text, nullable=True)
    corrected_text = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    source_refs = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)

    approved = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    benchmark_eligible = Column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    approved_by = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    @validates("original_text", "corrected_text", "reason")
    def _pseudonimizar(self, key, value):
        return pseudonimizar_texto_auditoria(value)
