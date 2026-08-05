from __future__ import annotations
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, func
from app.core.database import Base


class EjcSkill(Base):
    __tablename__ = "ejc_skills"

    id                    = Column(String(36), primary_key=True)
    name                  = Column(String(100), nullable=False, unique=True)
    display_name          = Column(String(200), nullable=False)
    description           = Column(Text, nullable=True)
    system_prompt         = Column(Text, nullable=False)
    engine                = Column(String(20), nullable=False, default="groq")
    area                  = Column(String(50), nullable=False, default="juridico")
    active                = Column(Boolean, nullable=False, default=True)
    requires_case         = Column(Boolean, nullable=False, default=False)
    requires_human_review = Column(Boolean, nullable=False, default=True)
    oab_restricted        = Column(Boolean, nullable=False, default=False)
    version               = Column(Integer, nullable=False, default=1)

    # Uso (Bloco 4 — enxugar catálogo, migration 130): AILog não distingue
    # qual skill gerou a chamada, então o contador vive aqui mesmo, mantido
    # por app/services/ai_skill_service.py a cada execução bem-sucedida.
    vezes_executado       = Column(Integer, nullable=False, default=0)
    ultima_execucao       = Column(DateTime(timezone=True), nullable=True)

    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
