# ── app/models/environmental.py ──────────────────────────────────────────────
# Módulo Ambiental — autos de infração IBAMA/órgãos estaduais
# Base legal: Decreto 6.514/2008 art. 113 (20 dias para defesa)
#             Lei 9.784/99 art. 66 §1º (prorrogação p/ dia útil)
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Date, Enum as SAEnum, func, Text, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class OrgaoAutuador(str, enum.Enum):
    IBAMA  = "IBAMA"
    IEF_MG = "IEF_MG"
    SEMAD_MG = "SEMAD_MG"
    FEAM_MG = "FEAM_MG"
    IGAM_MG = "IGAM_MG"
    ICMBio = "ICMBio"
    municipal = "municipal"
    outro  = "outro"


class StatusDefesa(str, enum.Enum):
    aguardando_ciencia = "aguardando_ciencia"
    prazo_correndo     = "prazo_correndo"
    elaborando         = "elaborando"
    protocolada        = "protocolada"
    julgada            = "julgada"
    recurso            = "recurso"
    conversao_multa    = "conversao_multa"
    encerrado          = "encerrado"


class EnvironmentalCase(Base):
    __tablename__ = "environmental_cases"

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, unique=True, index=True)

    # Auto de infração
    orgao_autuador = Column(SAEnum(OrgaoAutuador), nullable=False)
    numero_auto    = Column(String(50), nullable=False, index=True)
    data_lavratura = Column(Date, nullable=True)
    data_ciencia   = Column(Date, nullable=True)   # marco inicial do prazo

    especie_infracao = Column(Text, nullable=True)
    dispositivo_infringido = Column(String(255), nullable=True)  # ex: art. 70 Lei 9.605/98
    valor_multa      = Column(Numeric(14, 2), nullable=True)

    # Prazo de defesa (calculado automaticamente)
    prazo_defesa_dias  = Column(Numeric(3, 0), default=20)   # Decreto 6.514/08
    data_prazo_defesa  = Column(Date, nullable=True, index=True)  # com prorrogação legal
    status_defesa      = Column(SAEnum(StatusDefesa), nullable=False,
                                default=StatusDefesa.aguardando_ciencia, index=True)

    # Conversão de multa (Decreto 6.514/08 arts. 139-148)
    conversao_solicitada = Column(DateTime(timezone=True), nullable=True)
    valor_multa_convertida = Column(Numeric(14, 2), nullable=True)
    servico_ambiental    = Column(Text, nullable=True)

    # Dados ambientais
    area_degradada_ha = Column(Numeric(10, 2), nullable=True)
    bioma             = Column(String(50), nullable=True)
    coordenadas       = Column(String(100), nullable=True)
    embargo           = Column(String(20), nullable=True)   # sim|nao|parcial

    resultado_julgamento = Column(Text, nullable=True)
    observacoes          = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="environmental")
