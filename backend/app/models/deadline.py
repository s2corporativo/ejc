# ── app/models/deadline.py ───────────────────────────────────────────────────
from __future__ import annotations

import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class DeadlineTipo(str, enum.Enum):
    processual = "processual"
    administrativo = "administrativo"
    interno = "interno"
    audiencia = "audiencia"
    prescricao = "prescricao"


class DeadlineStatus(str, enum.Enum):
    pendente = "pendente"
    concluido = "concluido"
    vencido = "vencido"
    cancelado = "cancelado"


class DeadlinePrioridade(str, enum.Enum):
    baixa = "baixa"
    media = "media"
    alta = "alta"
    critica = "critica"


class Deadline(Base):
    __tablename__ = "deadlines"

    id = Column(String(36), primary_key=True)
    titulo = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    tipo = Column(
        SAEnum(DeadlineTipo), nullable=False, default=DeadlineTipo.processual
    )
    prioridade = Column(
        SAEnum(DeadlinePrioridade),
        nullable=False,
        default=DeadlinePrioridade.media,
    )
    status = Column(
        SAEnum(DeadlineStatus),
        nullable=False,
        default=DeadlineStatus.pendente,
        index=True,
    )

    data_prazo = Column(Date, nullable=False, index=True)
    data_intimacao = Column(Date, nullable=True)

    # Rastreabilidade do cálculo processual eletrônico. `data_intimacao` é a
    # data de ciência/disponibilização informada pelo fluxo; para DJEN, a
    # publicação e o termo inicial são conceitos jurídicos distintos e ficam
    # persistidos separadamente.
    data_publicacao = Column(Date, nullable=True)
    termo_inicial = Column(Date, nullable=True)
    regime_calculo = Column(String(20), nullable=True)  # civel|trabalhista|penal
    calculo_automatico = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    data_conclusao = Column(DateTime(timezone=True), nullable=True)
    concluido_por = Column(String(36), nullable=True)
    base_legal = Column(String(255), nullable=True)

    # Confirmação de ciência (audit LGPD)
    ciencia_confirmada = Column(Boolean, default=False)
    ciencia_confirmada_em = Column(DateTime(timezone=True), nullable=True)
    ciencia_confirmada_por = Column(String(36), nullable=True)

    # Alertas enviados (evita duplicação)
    alerta_7d_enviado = Column(Boolean, default=False)
    alerta_3d_enviado = Column(Boolean, default=False)
    alerta_1d_enviado = Column(Boolean, default=False)

    case_id = Column(
        String(36), ForeignKey("cases.id"), nullable=True, index=True
    )
    responsavel_id = Column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    observacoes = Column(Text, nullable=True)

    # Origem e rastreabilidade DataJud/DJEN.
    origem = Column(String(20), nullable=False, server_default="manual")
    referencia_datajud = Column(String(64), nullable=True, index=True)

    # Prazo extraído por IA nasce como rascunho a confirmar.
    confirmado = Column(Boolean, nullable=False, server_default=true())
    origem_documento_id = Column(
        String(36), ForeignKey("documents.id"), nullable=True, index=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="deadlines")
    responsavel = relationship(
        "User", foreign_keys=[responsavel_id], back_populates="deadlines"
    )
