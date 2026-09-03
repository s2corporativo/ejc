# ── app/models/djen.py ───────────────────────────────────────────────────────
# Intimações capturadas do DJEN (Diário de Justiça Eletrônico Nacional).
# A disponibilização é fato da fonte; publicação/termo inicial/regime só são
# preenchidos após revisão humana, nunca inferidos silenciosamente.
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class DjenComunicacao(Base):
    __tablename__ = "djen_comunicacoes"

    id = Column(String(36), primary_key=True)
    comunicacao_id_externo = Column(
        String(64), nullable=False, unique=True, index=True
    )
    advogado_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    numero_processo = Column(String(30), index=True)
    tribunal = Column(String(20))
    tipo_comunicacao = Column(String(60))
    data_disponibilizacao = Column(Date, index=True)
    # #968: marcos jurídicos revisados, separados da disponibilização.
    data_publicacao = Column(Date, nullable=True)
    termo_inicial = Column(Date, nullable=True)
    regime_calculo = Column(String(20), nullable=True)
    calculo_metadata = Column(JSONB, nullable=True)
    prazo_revisado_por = Column(String(36), nullable=True)
    prazo_revisado_em = Column(DateTime(timezone=True), nullable=True)

    texto_resumo = Column(Text)
    case_id = Column(
        String(36), ForeignKey("cases.id"), nullable=True, index=True
    )
    processada = Column(Boolean, default=False, index=True)
    processada_por = Column(String(36), nullable=True)
    processada_em = Column(DateTime(timezone=True), nullable=True)

    prazo_sugerido_status = Column(String(20), nullable=True, default="nenhum")
    prazo_deadline_id = Column(String(36), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
