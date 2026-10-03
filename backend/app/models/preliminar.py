"""Persistência única de preliminares de Raio-X e Sala Jurídica.

Os módulos antigos expõem adaptadores ORM com discriminador de origem,
nomes/defaults compatíveis e nenhuma tabela própria. A migration 171
migra os dados e mantém views legadas e espelho transacional de rollback.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, synonym

from app.core.database import Base

ORIGEM_PRELIMINAR = {"raio_x", "sala_juridica"}


class Preliminar(Base):
    """Análise preliminar de um caso, antes da conversão em `Case` oficial.

    Unifica `RaioXAnalise` (origem="raio_x") e `LegalChatSession`
    (origem="sala_juridica"). Colunas comuns não têm prefixo; colunas
    específicas de uma origem são sempre nullable.
    """

    __tablename__ = "preliminares"
    __table_args__ = (
        CheckConstraint("origem IN ('raio_x', 'sala_juridica')", name="ck_preliminares_origem"),
        Index("ix_preliminares_status_criado", "status", "created_at"),
        Index("ix_preliminares_criador_status", "created_by", "status"),
    )

    __mapper_args__ = {"polymorphic_on": "origem", "polymorphic_abstract": True}

    # ── Comuns às duas origens ────────────────────────────────────────────
    id = Column(String(36), primary_key=True)
    origem = Column(String(20), nullable=False, index=True)
    titulo = Column(String(255), nullable=False)
    status = Column(String(40), nullable=False, index=True)
    potencial_cliente = Column(String(255), nullable=True)
    area = Column(String(100), nullable=True, index=True)
    convertido_case_id = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # Retenção preservada do Raio-X; a Sala não ganha purga automática.
    retention_until = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    discarded_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Específicas de origem="raio_x" (RaioXAnalise) ────────────────────
    numero_processo = Column(String(30), nullable=True, index=True)
    subarea = Column(String(100), nullable=True)
    rito = Column(String(100), nullable=True)
    fase = Column(String(100), nullable=True)
    tribunal = Column(String(50), nullable=True)
    orgao = Column(String(100), nullable=True)
    unidade = Column(String(100), nullable=True)
    posicao_cliente = Column(String(100), nullable=True)
    risco_nivel = Column(String(30), nullable=True)
    prazo_urgente = Column(Boolean, nullable=True, default=False)
    # FK para o Case que CONTEXTUALIZOU a criação deste Raio-X — não confundir
    # com o discriminador `origem` (raio_x|sala_juridica) desta mesma tabela:
    # este campo é "a partir de qual caso" a análise nasceu, aquele é "qual
    # produto" a gerou.
    origem_contextual_case_id = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    dados_extraidos = Column(JSONB, nullable=True, default=dict)
    relatorio = Column(JSONB, nullable=True, default=dict)
    revisao_humana = Column(JSONB, nullable=True, default=dict)
    alertas_conflito = Column(JSONB, nullable=True, default=list)
    custo_ia = Column(JSONB, nullable=True, default=dict)

    # ── Específicas de origem="sala_juridica" (LegalChatSession) ─────────
    favorita = Column(Boolean, nullable=True, default=False)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True, index=True)
    advogado_responsavel_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    workspace_texto = Column(Text, nullable=True)
    workspace_versao = Column(Integer, nullable=True, default=0)
    frozen_at = Column(DateTime(timezone=True), nullable=True)
    custo_ia_total = Column(Numeric(12, 6), nullable=True, default=0)

    documentos = relationship(
        "PreliminarDocumento",
        back_populates="preliminar",
        cascade="all, delete-orphan",
        order_by="PreliminarDocumento.created_at",
    )
    mensagens = relationship(
        "PreliminarMensagem",
        back_populates="preliminar",
        cascade="all, delete-orphan",
        order_by="PreliminarMensagem.created_at",
    )
    estados = relationship(
        "PreliminarEstado",
        back_populates="preliminar",
        cascade="all, delete-orphan",
        order_by="PreliminarEstado.versao",
    )


class PreliminarDocumento(Base):
    """Documento anexado a uma preliminar. Unifica `RaioXDocumento` + `LegalChatAttachment`."""

    __tablename__ = "preliminar_documentos"
    __table_args__ = (
        UniqueConstraint("preliminar_id", "sha256", name="uq_preliminar_documento_hash"),
        Index("ix_preliminar_documentos_preliminar", "preliminar_id", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    preliminar_id = Column(String(36), ForeignKey("preliminares.id", ondelete="CASCADE"), nullable=False)
    nome_original = Column(String(255), nullable=False)
    filepath = Column(String(500), nullable=False)
    mimetype = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    tipo_documento = Column(String(100), nullable=True)
    paginas = Column(Integer, nullable=True)  # específico de origem="raio_x"
    ocr_utilizado = Column(Boolean, nullable=False, default=False)
    resultado_analise = Column(JSONB, nullable=False, default=dict)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    preliminar = relationship("Preliminar", back_populates="documentos")
    analise_id = synonym("preliminar_id")
    session_id = synonym("preliminar_id")
    analise = synonym("preliminar")
    sessao = synonym("preliminar")


class PreliminarMensagem(Base):
    """Mensagem de chat da preliminar. Só existe para origem="sala_juridica".

    Unifica `LegalChatMessage`; FK para `preliminares` mesmo assim.
    """

    __tablename__ = "preliminar_mensagens"
    __table_args__ = (Index("ix_preliminar_mensagens_preliminar", "preliminar_id", "created_at"),)

    id = Column(String(36), primary_key=True)
    preliminar_id = Column(String(36), ForeignKey("preliminares.id", ondelete="CASCADE"), nullable=False)
    autor = Column(String(10), nullable=False)  # "user" | "ia"
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    modo = Column(String(40), nullable=False, default="conversa_livre")
    conteudo = Column(Text, nullable=False)
    modelo = Column(String(120), nullable=True)
    agente = Column(String(120), nullable=True)
    skills = Column(JSONB, nullable=False, default=list)
    fontes = Column(JSONB, nullable=False, default=list)
    citacoes = Column(JSONB, nullable=False, default=list)
    alertas = Column(JSONB, nullable=False, default=list)
    tokens_input = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)
    custo_estimado = Column(Numeric(12, 6), nullable=True)
    ai_log_id = Column(String(36), ForeignKey("ai_logs.id"), nullable=True, index=True)
    estado_versao = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    preliminar = relationship("Preliminar", back_populates="mensagens")
    session_id = synonym("preliminar_id")
    sessao = synonym("preliminar")


class PreliminarEstado(Base):
    """Snapshot imutável do estado jurídico consolidado. Só existe para origem="sala_juridica".

    Unifica `LegalChatStateVersion`; FK para `preliminares` mesmo assim.
    """

    __tablename__ = "preliminar_estados"
    __table_args__ = (
        UniqueConstraint("preliminar_id", "versao", name="uq_preliminar_estado_versao"),
        Index("ix_preliminar_estados_preliminar", "preliminar_id", "versao"),
    )

    id = Column(String(36), primary_key=True)
    preliminar_id = Column(String(36), ForeignKey("preliminares.id", ondelete="CASCADE"), nullable=False)
    versao = Column(Integer, nullable=False)
    resumo = Column(Text, nullable=True)
    estado = Column(JSONB, nullable=False, default=dict)
    # Autoria da versão: "ia" (pós-resposta) ou "advogado" (edição manual).
    # Corresponde a LegalChatStateVersion.origem — renomeado para não colidir
    # com o discriminador `origem` de Preliminar (raio_x | sala_juridica).
    autoria = Column(String(20), nullable=False, default="advogado")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    preliminar = relationship("Preliminar", back_populates="estados")
    session_id = synonym("preliminar_id")
    origem = synonym("autoria")
    sessao = synonym("preliminar")
