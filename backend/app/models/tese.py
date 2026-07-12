# ── app/models/tese.py ────────────────────────────────────────────────────────
# Banco de Teses Jurídicas — repositório institucional de argumentos vencedores.
# Integrado ao RAG e à IA para reaproveitamento inteligente.
from __future__ import annotations
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Float, Integer, DateTime, ForeignKey, Enum as SAEnum,
)
from app.core.database import Base


class TeseTipo(str, enum.Enum):
    escritorio   = "escritorio"    # elaborada internamente
    sugerida_ia  = "sugerida_ia"  # gerada pela IA e validada
    doutrina     = "doutrina"     # fundamento doutrinário
    jurisprudencia = "jurisprudencia"  # baseada em julgado
    externa      = "externa"      # copiada de outro escritório / publicação


class TeseStatus(str, enum.Enum):
    rascunho  = "rascunho"
    ativa     = "ativa"
    arquivada = "arquivada"


class Tese(Base):
    __tablename__ = "teses"

    id           = Column(String(36), primary_key=True)
    titulo       = Column(String(300), nullable=False)
    descricao    = Column(Text, nullable=False)
    fundamentacao = Column(Text)           # artigos, súmulas, princípios
    jurisprudencia = Column(Text)          # julgados de suporte
    contra_argumento = Column(Text)        # o que o adversário pode responder
    area_juridica = Column(String(60))     # trabalhista, civel, ambiental...
    tribunal     = Column(String(120))     # ex: TRT-3, TJMG, STJ
    magistrado   = Column(String(200))     # magistrado associado (analytics)
    tags         = Column(Text)            # CSV: "responsabilidade,consumidor"
    observacoes  = Column(Text)

    tipo         = Column(SAEnum(TeseTipo),   nullable=False, default=TeseTipo.escritorio)
    status       = Column(SAEnum(TeseStatus), nullable=False, default=TeseStatus.ativa)

    # Métricas de desempenho
    vezes_usada  = Column(Integer, default=0, nullable=False)
    vezes_venceu = Column(Integer, default=0, nullable=False)
    vezes_perdeu = Column(Integer, default=0, nullable=False)
    taxa_sucesso = Column(Float)           # calculada: vezes_venceu/vezes_usada

    # Metadados
    created_by   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
    deleted_at   = Column(DateTime(timezone=True), nullable=True)  # soft-delete

    def __repr__(self):
        return f"<Tese {self.titulo[:40]}>"


class TeseCasoLink(Base):
    """Vínculo entre tese e caso (N:N) + resultado da aplicação."""
    __tablename__ = "tese_caso_links"

    id       = Column(String(36), primary_key=True)
    tese_id  = Column(String(36), ForeignKey("teses.id",  ondelete="CASCADE"), nullable=False)
    case_id  = Column(String(36), ForeignKey("cases.id",  ondelete="CASCADE"), nullable=False)
    resultado = Column(String(20))   # procedente | improcedente | acordo | pendente
    observacao = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
