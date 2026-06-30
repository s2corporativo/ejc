# ── app/models/djen.py ───────────────────────────────────────────────────────
# Intimações capturadas do DJEN (Diário de Justiça Eletrônico Nacional)
# via API Comunica/CNJ. Dedup pelo ID externo da comunicação.
from sqlalchemy import Column, String, Text, Date, Boolean, DateTime, func, ForeignKey
from app.core.database import Base


class DjenComunicacao(Base):
    __tablename__ = "djen_comunicacoes"

    id                     = Column(String(36), primary_key=True)
    comunicacao_id_externo = Column(String(64), nullable=False, unique=True, index=True)
    advogado_id            = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    numero_processo        = Column(String(30), index=True)
    tribunal               = Column(String(20))
    tipo_comunicacao       = Column(String(60))
    data_disponibilizacao  = Column(Date, index=True)
    texto_resumo           = Column(Text)
    case_id                = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    processada             = Column(Boolean, default=False, index=True)
    processada_por         = Column(String(36), nullable=True)
    processada_em          = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
