# ── app/models/analise_caso_ia.py ────────────────────────────────────────────
# Módulo "Análise de Caso IA" — chat conversacional multi-turno em que a IA age
# como advogado sênior. Duas tabelas:
#   • analise_caso_sessoes  — uma conversa (do usuário; opcionalmente atada a caso)
#   • analise_caso_mensagens — turnos user/assistant persistidos (histórico)
#
# Estilo espelhado de models/ai_log.py: String(36) PK com default uuid4, FKs para
# users.id/cases.id, DateTime(timezone=True) com server_default now() e
# relationship com cascade delete-orphan.
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    false,
    func,
    true,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class AnaliseCasoSessao(Base):
    __tablename__ = "analise_caso_sessoes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # Caso opcional: ao ser apagado o caso, a sessão sobrevive (SET NULL).
    case_id = Column(
        String(36),
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    titulo = Column(String(200), nullable=False, default="Nova análise")
    # "padrao" | "alto" | "maximo" (nível de inteligência do gateway).
    nivel = Column(String(20), nullable=False, default="alto")
    area = Column(String(80), nullable=True)
    # Espelha a migration 113 (nullable=False + server_default false) para que um
    # futuro autogenerate não emita ALTER espúrio.
    arquivada = Column(
        Boolean, nullable=False, server_default=false(), default=False, index=True
    )

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    mensagens = relationship(
        "AnaliseCasoMensagem",
        back_populates="sessao",
        cascade="all, delete-orphan",
        order_by="AnaliseCasoMensagem.created_at",
    )


class AnaliseCasoMensagem(Base):
    __tablename__ = "analise_caso_mensagens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    sessao_id = Column(
        String(36),
        ForeignKey("analise_caso_sessoes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "user" | "assistant" (formato OpenAI de papéis).
    papel = Column(String(16), nullable=False)
    # Texto exibido na bolha do chat.
    conteudo = Column(Text, nullable=False)
    # OCR do documento OU texto colado: entra no prompt, NÃO é exibido inteiro
    # na bolha (só o resumo/chip de anexo).
    contexto_anexo = Column(Text, nullable=True)
    # Nome do arquivo OU "Texto colado".
    anexo_nome = Column(String(255), nullable=True)
    # Link ao AILog da resposta assistant (rastro de auditoria/HITL).
    ai_log_id = Column(String(36), nullable=True)
    # Toda resposta de IA nasce rascunho (HITL/OAB) até revisão humana.
    # Espelha a migration 113 (nullable=False + server_default true).
    is_rascunho = Column(
        Boolean, nullable=False, server_default=true(), default=True
    )

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    sessao = relationship("AnaliseCasoSessao", back_populates="mensagens")
