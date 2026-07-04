# ── app/models/ai_log.py ─────────────────────────────────────────────────────
# Registro de TODO uso de IA (Groq). LGPD + OAB compliance.
# prompt_sanitizado = o que foi enviado (SEM PII); status HITL rastreado.
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, Text, Boolean, Integer, Numeric, ForeignKey
from sqlalchemy.orm import relationship, validates
from app.core.database import Base
import enum


# BUG-22: nome do modelo canônico. O gateway às vezes gravava o modelo sem o
# prefixo do provedor (ex.: "llama-3.3-70b-versatile") e às vezes com
# ("groq/llama-3.3-70b-versatile"). Normalizamos no WRITE path (validador do ORM)
# para que TODO ai_log persista sempre a forma canônica com provedor.
def normalizar_modelo_ia(modelo: str | None) -> str | None:
    if not modelo:
        return modelo
    m = modelo.strip()
    if not m:
        return m
    # Já tem provedor (contém "/") → mantém como está.
    if "/" in m:
        return m
    # Sem provedor: modelos Groq/Llama recebem o prefixo canônico.
    if m.lower().startswith("llama"):
        return f"groq/{m}"
    return m


class AIStatusHITL(str, enum.Enum):
    gerado    = "gerado"        # IA respondeu, ninguém revisou
    revisado  = "revisado"      # humano revisou
    aplicado  = "aplicado"      # advogado aplicou ao caso/peça
    descartado = "descartado"


class AITipoUso(str, enum.Enum):
    analise_caso    = "analise_caso"      # sugestão de teses
    redacao_peca    = "redacao_peca"
    consulta_rag    = "consulta_rag"
    resumo_documento = "resumo_documento"
    outro           = "outro"


class AILog(Base):
    __tablename__ = "ai_logs"

    id      = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    case_id = Column(String(36), nullable=True, index=True)

    tipo_uso = Column(SAEnum(AITipoUso), nullable=False)
    modelo   = Column(String(50), nullable=False)   # ex: llama3-70b-8192

    # LGPD: registramos apenas o prompt SANITIZADO (sem PII)
    prompt_sanitizado  = Column(Text, nullable=False)
    pii_removida       = Column(Boolean, default=False)  # flag: houve remoção?
    resposta           = Column(Text, nullable=True)
    fontes_rag         = Column(Text, nullable=True)     # chunks usados (rastreabilidade)
    tokens_input       = Column(Integer, nullable=True)
    tokens_output      = Column(Integer, nullable=True)
    # Custo estimado da chamada em R$ (0 p/ Ollama local; calculado p/ Groq)
    custo_estimado     = Column(Numeric(12, 6), nullable=True)

    # HITL
    status_hitl  = Column(SAEnum(AIStatusHITL), nullable=False, default=AIStatusHITL.gerado, index=True)
    revisado_por = Column(String(36), nullable=True)
    revisado_em  = Column(DateTime(timezone=True), nullable=True)

    # Feedback do usuário sobre a resposta (feature #4 / migration 066):
    # 'util' | 'nao_util' | None (sem feedback).
    feedback     = Column(String(20), nullable=True)
    feedback_em  = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", foreign_keys=[user_id], back_populates="ai_logs")

    @validates("modelo")
    def _normalizar_modelo(self, key, value):
        # BUG-22: canoniza o nome do modelo em qualquer INSERT (todos os
        # write paths passam por aqui — ai_gateway/ai_service/peca_service/etc.).
        return normalizar_modelo_ia(value)
