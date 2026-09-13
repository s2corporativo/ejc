"""Despesa processual vinculada ao caso.

É custo do processo reembolsável ao cliente e NÃO `office_expenses`, que
representa overhead do escritório. O lançamento permanece cru até faturamento
explícito gerar um Fee do tipo `custas_despesas`.
"""
from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String, func

from app.core.database import Base


class CaseDespesa(Base):
    __tablename__ = "case_despesas"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    data = Column(Date, nullable=False)
    valor = Column(Numeric(14, 2), nullable=False)
    descricao = Column(String(500), nullable=False)
    categoria = Column(String(30), nullable=False, default="outro")
    fee_id = Column(String(36), ForeignKey("fees.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
