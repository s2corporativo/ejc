# ── app/models/prompt_juridico.py ─────────────────────────────────────────────
# Biblioteca de Prompts Jurídicos — reutilização e padronização de prompts de IA.
from __future__ import annotations
import enum

from sqlalchemy import (
    Column, String, Text, Integer, Boolean, Float,
    DateTime, ForeignKey, Enum as SAEnum, func,
)
from app.core.database import Base


class PromptCategoria(str, enum.Enum):
    peticao      = "peticao"
    contrato     = "contrato"
    audiencia    = "audiencia"
    email        = "email"
    modelo       = "modelo"
    analise      = "analise"
    resumo       = "resumo"
    negociacao   = "negociacao"
    outros       = "outros"


class PromptJuridico(Base):
    __tablename__ = "prompts_juridicos"

    id               = Column(String(36), primary_key=True)
    titulo           = Column(String(200), nullable=False)
    categoria        = Column(SAEnum(PromptCategoria, name="promptcategoria"), nullable=False)
    conteudo         = Column(Text, nullable=False)          # pode ter {{variavel}} como placeholders
    descricao        = Column(Text)                          # para que serve, como usar
    variaveis        = Column(Text)                          # JSON: ["variavel1", "variavel2"]
    tags             = Column(Text)
    favorito         = Column(Boolean, nullable=False, default=False)
    publico          = Column(Boolean, nullable=False, default=True)   # visível para todos do escritório

    # Métricas de uso
    vezes_executado  = Column(Integer, nullable=False, default=0)
    ultima_execucao  = Column(DateTime(timezone=True))
    avaliacao_media  = Column(Float)   # 1-5, média das avaliações de execução

    # Versionamento simples
    versao           = Column(Integer, nullable=False, default=1)

    # Auditoria
    created_by       = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at       = Column(DateTime(timezone=True), nullable=True)
