# ── app/models/estilo_advogado.py ────────────────────────────────────────────
# Aprendizado de Estilo — perfil de redação destilado por advogado.
# A partir de peças aprovadas, a IA destila tom, formalidade, conectivos,
# estrutura e expressões recorrentes do advogado; o perfil é reinjetado na
# etapa de redação do pipeline de peças (opt-in por advogado + flag por request).
# Um perfil por advogado (user_id UNIQUE).
from __future__ import annotations

from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, ForeignKey, func,
)

from app.core.database import Base


class EstiloAdvogado(Base):
    __tablename__ = "estilos_advogado"

    id = Column(String(36), primary_key=True)
    # Um perfil por advogado (UNIQUE) — ownership estrito é feito no service/router.
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Estilo destilado (tom, formalidade, conectivos, estrutura, expressões).
    perfil_estilo = Column(Text, nullable=True)
    # Quantas peças aprovadas já alimentaram o perfil.
    n_amostras = Column(Integer, nullable=False, default=0)
    # Advogado quer usar o estilo na geração de peças?
    ativo = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<EstiloAdvogado user={self.user_id} n={self.n_amostras}>"
