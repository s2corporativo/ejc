from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, String, Text, func

from app.core.database import Base


class SystemModuleSetting(Base):
    """Override operacional; não concede permissões e não substitui RBAC."""

    __tablename__ = "system_module_settings"

    module_key = Column(String(100), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=True)
    menu_visible = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False, default="active")
    replacement_route = Column(String(255), nullable=True)
    removal_date = Column(Date, nullable=True)
    reason = Column(Text, nullable=True)
    updated_by = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
