"""Preliminares — fundação de schema da fusão Raio-X + Sala Jurídica (F5, Fase 1).

Contexto (Issue #799, `docs/PLANO_FUSAO_CASO_UNICO.md`): `raio_x_analises` e
`legal_chat_sessions` modelam o MESMO conceito de produto — uma análise
preliminar de um caso antes dele virar `Case` oficial — em duas tabelas
físicas separadas, resíduo de quando Raio-X e Sala Jurídica eram telas
distintas. Esta Fase 1 é estritamente ADITIVA: cria o schema unificado
(`preliminares` + 3 tabelas filhas) sem tocar nas tabelas antigas, sem
migrar dado e sem alterar nenhum service/router. `raio_x_service.py` e
`legal_chat_service.py` continuam sendo a fonte de dados em produção.

Próximos passos (NÃO fazem parte desta fase — deixados para o futuro):
  Fase 2 — backfill do dado histórico + dual-write nos services existentes.
  Fase 3 — cutover dos consumidores (routers/services) para `preliminares` e
           aposentadoria (DROP, com backup) de `raio_x_analises`,
           `raio_x_documentos`, `legal_chat_sessions`, `legal_chat_messages`,
           `legal_chat_attachments` e `legal_chat_state_versions`.

Discriminador `origem` (`raio_x` | `sala_juridica`): colunas específicas de
cada origem ficam nullable — nula quando não fizer sentido para aquela
origem. Nomes que description a MESMA coisa nas duas tabelas de origem foram
unificados num único nome canônico:
  - `potencial_cliente` (RaioXAnalise.potencial_cliente == LegalChatSession.cliente_potencial)
  - `area`              (RaioXAnalise.area == LegalChatSession.area_sugerida; ampliado p/ String(100))

`preliminar_estados.autoria` corresponde a `LegalChatStateVersion.origem`
("ia" | "advogado") — renomeado aqui para não colidir semanticamente com o
discriminador `origem` da tabela-mãe (que distingue Raio-X de Sala Jurídica).
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
from sqlalchemy.orm import relationship

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
        CheckConstraint(
            "origem IN ('raio_x', 'sala_juridica')", name="ck_preliminares_origem"
        ),
        Index("ix_preliminares_status_criado", "status", "created_at"),
        Index("ix_preliminares_criador_status", "created_by", "status"),
    )

    # ── Comuns às duas origens ────────────────────────────────────────────
    id = Column(String(36), primary_key=True)
    origem = Column(String(20), nullable=False, index=True)
    titulo = Column(String(255), nullable=False)
    status = Column(String(40), nullable=False, index=True)
    potencial_cliente = Column(String(255), nullable=True)
    area = Column(String(100), nullable=True)
    convertido_case_id = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # ── Específicas de origem="raio_x" (RaioXAnalise) ────────────────────
    numero_processo = Column(String(30), nullable=True)
    subarea = Column(String(100), nullable=True)
    rito = Column(String(100), nullable=True)
    fase = Column(String(100), nullable=True)
    tribunal = Column(String(50), nullable=True)
    orgao = Column(String(100), nullable=True)
    unidade = Column(String(100), nullable=True)
    posicao_cliente = Column(String(100), nullable=True)
    risco_nivel = Column(String(30), nullable=True)
    prazo_urgente = Column(Boolean, nullable=True, default=False)
    origem_contextual_case_id = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    dados_extraidos = Column(JSONB, nullable=True, default=dict)
    relatorio = Column(JSONB, nullable=True, default=dict)
    revisao_humana = Column(JSONB, nullable=True, default=dict)
    alertas_conflito = Column(JSONB, nullable=True, default=list)
    custo_ia = Column(JSONB, nullable=True, default=dict)
    retention_until = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    discarded_at = Column(DateTime(timezone=True), nullable=True)

    # ── Específicas de origem="sala_juridica" (LegalChatSession) ─────────
    favorita = Column(Boolean, nullable=True, default=False)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True, index=True)
    advogado_responsavel_id = Column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    workspace_texto = Column(Text, nullable=True)
    workspace_versao = Column(Integer, nullable=True, default=0)
    frozen_at = Column(DateTime(timezone=True), nullable=True)
    custo_ia_total = Column(Numeric(12, 6), nullable=True, default=0)

    documentos = relationship(
        "PreliminarDocumento", back_populates="preliminar", cascade="all, delete-orphan",
        order_by="PreliminarDocumento.created_at",
    )
    mensagens = relationship(
        "PreliminarMensagem", back_populates="preliminar", cascade="all, delete-orphan",
        order_by="PreliminarMensagem.created_at",
    )
    estados = relationship(
        "PreliminarEstado", back_populates="preliminar", cascade="all, delete-orphan",
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
    preliminar_id = Column(
        String(36), ForeignKey("preliminares.id", ondelete="CASCADE"), nullable=False
    )
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


class PreliminarMensagem(Base):
    """Mensagem de chat da preliminar. Só existe para origem="sala_juridica".

    Unifica `LegalChatMessage`; FK para `preliminares` mesmo assim.
    """

    __tablename__ = "preliminar_mensagens"
    __table_args__ = (
        Index("ix_preliminar_mensagens_preliminar", "preliminar_id", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    preliminar_id = Column(
        String(36), ForeignKey("preliminares.id", ondelete="CASCADE"), nullable=False
    )
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
    preliminar_id = Column(
        String(36), ForeignKey("preliminares.id", ondelete="CASCADE"), nullable=False
    )
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
