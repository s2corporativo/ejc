# ── app/models/procuracao.py ─────────────────────────────────────────────────
# Controle de procurações: poderes, validade, alertas de vencimento.
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Date, func, Text, Boolean, ForeignKey
from app.core.database import Base


class Procuracao(Base):
    __tablename__ = "procuracoes"

    id        = Column(String(36), primary_key=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)

    tipo_poderes = Column(String(30), nullable=False, default="ad_judicia")
    # ad_judicia | ad_judicia_et_extra | especiais
    poderes_especiais = Column(Text, nullable=True)   # receber citação, transigir, etc.
    permite_substabelecimento = Column(Boolean, default=True)

    data_outorga  = Column(Date, nullable=False)
    data_validade = Column(Date, nullable=True, index=True)  # NULL = prazo indeterminado
    foro_restrito = Column(String(100), nullable=True)

    document_id   = Column(String(36), nullable=True)  # PDF da procuração no GED
    alerta_30d_enviado = Column(Boolean, default=False)
    revogada      = Column(Boolean, default=False)
    revogada_em   = Column(Date, nullable=True)

    observacoes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
