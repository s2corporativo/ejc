# ── app/models/legal_doc.py ──────────────────────────────────────────────────
# Peças jurídicas com HITL obrigatório:
# ai_generated=True NUNCA avança para aprovado sem human_reviewed=True
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, Text, Boolean, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class PecaTipo(str, enum.Enum):
    peticao_inicial = "peticao_inicial"
    contestacao     = "contestacao"
    recurso         = "recurso"
    contrarrazoes   = "contrarrazoes"
    parecer         = "parecer"
    contrato        = "contrato"
    procuracao      = "procuracao"
    notificacao_extrajudicial = "notificacao_extrajudicial"
    defesa_ambiental = "defesa_ambiental"
    outro           = "outro"


class PecaStatus(str, enum.Enum):
    rascunho   = "rascunho"
    em_revisao = "em_revisao"
    corrigida  = "corrigida"
    aprovada   = "aprovada"
    final      = "final"
    protocolada = "protocolada"


class LegalDoc(Base):
    __tablename__ = "legal_docs"

    id        = Column(String(36), primary_key=True)
    titulo    = Column(String(255), nullable=False)
    tipo_peca = Column(SAEnum(PecaTipo), nullable=False)
    status    = Column(SAEnum(PecaStatus), nullable=False, default=PecaStatus.rascunho, index=True)
    conteudo  = Column(Text, nullable=False)          # markdown
    versao    = Column(Integer, default=1)

    # ── Controle/versionamento (Fase D) ──────────────────────────────────
    # `area`: ramo do direito da geração (chave de AREAS_DIREITO).
    # `codigo_peca`: identificador estável por ramo EJC-<SIGLA>-<NNN>,
    # reservado atomicamente em app.services.peca_numeracao. Nullable p/ peças
    # antigas geradas antes do versionamento.
    area        = Column(String(40), nullable=True)
    codigo_peca = Column(String(30), nullable=True, index=True)

    # ── HITL — Human-in-the-Loop (obrigatório p/ IA) ────────────────────
    ai_generated   = Column(Boolean, default=False, nullable=False)
    human_reviewed = Column(Boolean, default=False, nullable=False)
    revisor_id     = Column(String(36), ForeignKey("users.id"), nullable=True)
    revisado_em    = Column(DateTime(timezone=True), nullable=True)
    notas_revisao  = Column(Text, nullable=True)

    case_id    = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    created_by = Column(String(36), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case    = relationship("Case", back_populates="legal_docs")
    revisor = relationship("User", foreign_keys=[revisor_id], back_populates="legal_docs_revisados")
