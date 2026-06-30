# ── app/models/bank_analysis.py ──────────────────────────────────────────────
# Módulo de Análise Bancária (extratos): detecta cobranças abusivas.
# Distinto de analise_bancaria.py (que analisa CONTRATOS via IA). Aqui é
# determinístico: parser de extrato + motor de regras com base legal.
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Date, Integer, Numeric, Text, func
from app.core.database import Base


class BankAnalysis(Base):
    __tablename__ = "bank_analyses"
    id              = Column(String(36), primary_key=True)
    case_id         = Column(String(36), nullable=True, index=True)
    client_id       = Column(String(36), nullable=True, index=True)
    banco           = Column(String(60), nullable=True)
    formato         = Column(String(10), nullable=True)   # pdf|ofx|csv
    arquivo_nome    = Column(String(255), nullable=True)
    periodo_inicio  = Column(Date, nullable=True)
    periodo_fim     = Column(Date, nullable=True)
    total_transacoes = Column(Integer, default=0)
    total_creditos  = Column(Numeric(14, 2), default=0)
    total_debitos   = Column(Numeric(14, 2), default=0)
    total_abusivo   = Column(Numeric(14, 2), default=0)
    qtd_abusivas    = Column(Integer, default=0)
    status          = Column(String(20), default="processando")  # processando|concluido|erro
    erro            = Column(Text, nullable=True)
    created_by      = Column(String(36), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at      = Column(DateTime(timezone=True), nullable=True)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    id          = Column(String(36), primary_key=True)
    analysis_id = Column(String(36), nullable=False, index=True)
    data        = Column(Date, nullable=True)
    descricao   = Column(String(500), nullable=True)
    valor       = Column(Numeric(14, 2), nullable=True)
    tipo        = Column(String(10), nullable=True)   # credito|debito
    saldo       = Column(Numeric(14, 2), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class BankAbusiveCharge(Base):
    __tablename__ = "bank_abusive_charges"
    id             = Column(String(36), primary_key=True)
    analysis_id    = Column(String(36), nullable=False, index=True)
    transaction_id = Column(String(36), nullable=True)
    regra          = Column(String(40), nullable=True)
    titulo         = Column(String(200), nullable=True)
    descricao      = Column(Text, nullable=True)
    base_legal     = Column(String(255), nullable=True)
    prioridade     = Column(String(10), nullable=True)   # URGENTE|MEDIO|BAIXO
    valor          = Column(Numeric(14, 2), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
