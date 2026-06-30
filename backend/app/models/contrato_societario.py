# ── app/models/contrato_societario.py ────────────────────────────────────────
# Gestão de contratos societários — ciclo de vida completo.
from __future__ import annotations
import enum

from sqlalchemy import (
    Column, String, Text, Numeric, Integer, Boolean,
    Date, DateTime, ForeignKey, Enum as SAEnum, func,
)
from app.core.database import Base


class StatusContrato(str, enum.Enum):
    rascunho    = "rascunho"
    em_revisao  = "em_revisao"
    aprovado    = "aprovado"
    assinado    = "assinado"
    vigente     = "vigente"
    suspenso    = "suspenso"
    expirado    = "expirado"
    rescindido  = "rescindido"


class TipoContrato(str, enum.Enum):
    prestacao_servicos = "prestacao_servicos"
    honorarios         = "honorarios"
    parceria           = "parceria"
    fornecimento       = "fornecimento"
    nda                = "nda"
    societario         = "societario"
    locacao            = "locacao"
    outros             = "outros"


class ContratoSocietario(Base):
    __tablename__ = "contratos_societarios"

    id                        = Column(String(36), primary_key=True)
    titulo                    = Column(String(300), nullable=False)
    tipo                      = Column(SAEnum(TipoContrato, name="tipocontrato"), nullable=False)
    status                    = Column(SAEnum(StatusContrato, name="statuscontrato"),
                                       nullable=False, server_default="rascunho")

    # Partes e objeto
    partes                    = Column(Text)         # texto livre ou JSON com nomes/CNPJs
    objeto                    = Column(Text, nullable=False)
    clausulas_especiais       = Column(Text)

    # Valores
    valor_total               = Column(Numeric(15, 2))
    moeda                     = Column(String(3), default="BRL")
    periodicidade             = Column(String(30))   # mensal|trimestral|anual|único

    # Datas
    data_assinatura           = Column(Date)
    data_inicio               = Column(Date)
    data_fim                  = Column(Date)
    renovacao_automatica      = Column(Boolean, nullable=False, default=False)
    prazo_aviso_rescisao_dias = Column(Integer, default=30)
    alertar_dias_antes        = Column(Integer, default=60)  # alertar renovação X dias antes

    # Documento físico
    documento_id              = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"),
                                       nullable=True)

    # Vínculo opcional com case/client
    case_id                   = Column(String(36), ForeignKey("cases.id",   ondelete="SET NULL"), nullable=True)
    client_id                 = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)

    observacoes               = Column(Text)
    tags                      = Column(Text)
    created_by                = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at                = Column(DateTime(timezone=True), server_default=func.now())
    updated_at                = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at                = Column(DateTime(timezone=True), nullable=True)


class ContratoHistorico(Base):
    """Auditoria de mudanças de status do contrato."""
    __tablename__ = "contrato_historico"

    id            = Column(String(36), primary_key=True)
    contrato_id   = Column(String(36), ForeignKey("contratos_societarios.id", ondelete="CASCADE"),
                            nullable=False)
    status_de     = Column(String(30))
    status_para   = Column(String(30))
    observacao    = Column(Text)
    alterado_por  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    alterado_em   = Column(DateTime(timezone=True), server_default=func.now())
