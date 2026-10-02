# ── app/models/djen.py ───────────────────────────────────────────────────────
# Intimações capturadas do DJEN (Diário de Justiça Eletrônico Nacional)
# via API Comunica/CNJ. Dedup pelo ID externo da comunicação.
from sqlalchemy import Column, String, Text, Date, Boolean, DateTime, Index, func, ForeignKey
from app.core.database import Base


class DjenComunicacao(Base):
    __tablename__ = "djen_comunicacoes"

    id                     = Column(String(36), primary_key=True)
    # Única POR ADVOGADO (migration 169): a mesma comunicação pode ser destinada
    # a mais de um advogado do escritório e cada um precisa recebê-la.
    comunicacao_id_externo = Column(String(64), nullable=False, index=True)
    advogado_id            = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    numero_processo        = Column(String(30), index=True)
    tribunal               = Column(String(20))
    tipo_comunicacao       = Column(String(60))
    data_disponibilizacao  = Column(Date, index=True)
    texto_resumo           = Column(Text)
    # Evidência oficial (migration 169): texto íntegro sem tags, link do PDF e
    # órgão — necessários para conferir publicação/termo inicial na fonte.
    texto_integral         = Column(Text, nullable=True)
    link_oficial           = Column(Text, nullable=True)
    orgao                  = Column(String(255), nullable=True)
    case_id                = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    processada             = Column(Boolean, default=False, index=True)
    processada_por         = Column(String(36), nullable=True)
    processada_em          = Column(DateTime(timezone=True), nullable=True)

    # Prazo assistido (feature #1 / migration 065): o sistema SUGERE um prazo a
    # partir da intimação e o advogado ACEITA/RECUSA.
    # prazo_sugerido_status: 'nenhum' | 'sugerido' | 'aceito' | 'recusado'.
    prazo_sugerido_status  = Column(String(20), nullable=True, default="nenhum")
    # FK LÓGICA para deadlines.id (sem constraint física — mesmo padrão de
    # processada_por): id do Deadline criado quando o prazo é aceito.
    prazo_deadline_id      = Column(String(36), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "uq_djen_comunicacao_externo_advogado",
            "comunicacao_id_externo",
            "advogado_id",
            unique=True,
        ),
    )
