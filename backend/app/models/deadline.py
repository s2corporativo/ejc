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
from sqlalchemy.dialects.postgresql import JSONB
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


def _origem_exige_confirmacao_humana(origem: str | None) -> bool:
    valor = (origem or "").strip().lower()
    return valor in {"datajud", "importacao_ia"} or valor.startswith("ia_")


def _prioridade_critica(valor) -> bool:
    return getattr(valor, "value", valor) == DeadlinePrioridade.critica.value


class Deadline(Base):
    __tablename__ = "deadlines"

    def __init__(self, **kwargs):
        if "confirmado" not in kwargs and _origem_exige_confirmacao_humana(
            kwargs.get("origem")
        ):
            kwargs["confirmado"] = False
        # #717: nenhuma nova materialização crítica pode nascer já conferida,
        # mesmo se um caller legado tentar passar confirmado=True. A segunda
        # validação ocorre pelo endpoint canônico /deadlines/{id}/confirmar.
        if _prioridade_critica(kwargs.get("prioridade")):
            kwargs["confirmado"] = False
            kwargs["conferido_por"] = None
            kwargs["conferido_em"] = None
        super().__init__(**kwargs)

    id = Column(String(36), primary_key=True)
    titulo = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    tipo = Column(SAEnum(DeadlineTipo), nullable=False, default=DeadlineTipo.processual)
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
    # `data_intimacao` é legado e NÃO deve ser reinterpretada silenciosamente.
    data_intimacao = Column(Date, nullable=True)
    # #968: marcos jurídicos separados. Nenhum backfill inventa estes valores.
    data_publicacao = Column(Date, nullable=True)
    termo_inicial = Column(Date, nullable=True)
    regime_calculo = Column(String(20), nullable=True)
    # Snapshot reproduzível do cálculo/revisão: dias, tribunal, flags,
    # calendario_status, resultado_preliminar, modo e demais parâmetros seguros.
    calculo_metadata = Column(JSONB, nullable=True)
    calculado_por = Column(String(36), nullable=True)
    conferido_por = Column(String(36), nullable=True)
    conferido_em = Column(DateTime(timezone=True), nullable=True)

    data_conclusao = Column(DateTime(timezone=True), nullable=True)
    concluido_por = Column(String(36), nullable=True)
    base_legal = Column(String(255), nullable=True)

    ciencia_confirmada = Column(Boolean, default=False)
    ciencia_confirmada_em = Column(DateTime(timezone=True), nullable=True)
    ciencia_confirmada_por = Column(String(36), nullable=True)

    alerta_7d_enviado = Column(Boolean, default=False)
    alerta_3d_enviado = Column(Boolean, default=False)
    alerta_1d_enviado = Column(Boolean, default=False)

    case_id = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    responsavel_id = Column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    observacoes = Column(Text, nullable=True)

    origem = Column(String(20), nullable=False, server_default="manual")
    referencia_datajud = Column(String(64), nullable=True, index=True)
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
