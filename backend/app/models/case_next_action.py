# ── app/models/case_next_action.py ───────────────────────────────────────────
"""Próxima ação operacional do caso e exceções temporárias auditáveis."""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


URGENCIES = ("baixa", "media", "alta", "critica")
WAITING_ON = ("ninguem", "cliente", "terceiro", "tribunal", "interno")
ORIGIN_TYPES = ("manual", "documento", "movimento", "prazo", "tarefa")


class CaseNextAction(Base):
    """Uma ação por vez permanece atual; conclusões preservam o histórico."""

    __tablename__ = "case_next_actions"
    __table_args__ = (
        CheckConstraint(
            "urgency IN ('baixa','media','alta','critica')",
            name="ck_case_next_actions_urgency",
        ),
        CheckConstraint(
            "waiting_on IN ('ninguem','cliente','terceiro','tribunal','interno')",
            name="ck_case_next_actions_waiting_on",
        ),
        CheckConstraint(
            "origin_type IN ('manual','documento','movimento','prazo','tarefa')",
            name="ck_case_next_actions_origin_type",
        ),
        CheckConstraint(
            "(blocked = false) OR "
            "(blocked_reason IS NOT NULL AND length(trim(blocked_reason)) >= 5)",
            name="ck_case_next_actions_blocked_reason",
        ),
        CheckConstraint(
            "(waiting_on = 'ninguem') OR blocked = true",
            name="ck_case_next_actions_waiting_requires_block",
        ),
        Index("ix_case_next_actions_case_id", "case_id"),
        Index("ix_case_next_actions_owner_id", "owner_id"),
        Index("ix_case_next_actions_due_at", "due_at"),
        Index(
            "uq_case_next_actions_current",
            "case_id",
            unique=True,
            postgresql_where=text("completed_at IS NULL"),
        ),
    )

    id = Column(String(36), primary_key=True)
    case_id = Column(
        String(36),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(255), nullable=False)
    owner_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    due_at = Column(DateTime(timezone=True), nullable=False)
    urgency = Column(String(12), nullable=False, server_default="media")
    blocked = Column(Boolean, nullable=False, server_default=text("false"))
    blocked_reason = Column(Text, nullable=True)
    waiting_on = Column(String(20), nullable=False, server_default="ninguem")
    origin_type = Column(String(20), nullable=False, server_default="manual")
    origin_id = Column(String(36), nullable=True)

    created_by = Column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by = Column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    completion_note = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    case = relationship("Case")
    owner = relationship("User", foreign_keys=[owner_id])
    creator = relationship("User", foreign_keys=[created_by])
    completer = relationship("User", foreign_keys=[completed_by])


class CaseNextActionWaiver(Base):
    """Exceção temporária; nunca autoriza caso sem ação indefinidamente."""

    __tablename__ = "case_next_action_waivers"
    __table_args__ = (
        CheckConstraint(
            "length(trim(reason)) >= 10",
            name="ck_case_next_action_waivers_reason",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_case_next_action_waivers_expiry",
        ),
        Index("ix_case_next_action_waivers_case_id", "case_id"),
        Index(
            "uq_case_next_action_waivers_current",
            "case_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id = Column(String(36), primary_key=True)
    case_id = Column(
        String(36),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    case = relationship("Case")
    creator = relationship("User", foreign_keys=[created_by])
    revoker = relationship("User", foreign_keys=[revoked_by])
