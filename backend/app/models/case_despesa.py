# ── app/models/case_despesa.py ────────────────────────────────────────────────
"""Despesa processual lançada pelo advogado no caso (F3.2 / Issue #806).

Mesmo padrão de TimeEntry (models/time_entry.py): lançamento cru, sem valor
faturado até uma consolidação explícita (`faturar`) gerar um Fee
(tipo=custas_despesas). Não confundir com `office_expenses` (SQL bruto,
overhead do escritório, RBAC restrito a gestão/financeiro) — despesa
PROCESSUAL é lançada por quem trabalha o caso e existe para ser reembolsada
pelo cliente, não para controlar o caixa do escritório.
"""
from sqlalchemy import Column, String, Numeric, Date, DateTime, func, ForeignKey
from app.core.database import Base


class CaseDespesa(Base):
    __tablename__ = "case_despesas"

    id        = Column(String(36), primary_key=True)
    case_id   = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    user_id   = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    data      = Column(Date, nullable=False)
    valor     = Column(Numeric(14, 2), nullable=False)
    descricao = Column(String(500), nullable=False)
    categoria = Column(String(30), nullable=False, default="outro")
    fee_id    = Column(String(36), ForeignKey("fees.id"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
