# ── app/models/push.py ───────────────────────────────────────────────────────
from sqlalchemy import Column, String, DateTime, func, ForeignKey
from app.core.database import Base


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id       = Column(String(36), primary_key=True)
    user_id  = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    endpoint = Column(String(500), nullable=False, unique=True)
    p256dh   = Column(String(255), nullable=False)
    auth     = Column(String(255), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
