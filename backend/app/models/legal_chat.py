"""Sala Jurídica Conversacional — chat jurídico persistido (V1).

Porta de entrada conversacional do EJC: o advogado conversa livremente,
anexa documentos e a análise evolui em versões de estado jurídico até a
conversão controlada em caso. Substitui as antigas sala_de_guerra /
/sala-analise como superfície conversacional (o backend Raio-X permanece
como triagem autônoma de documentos).

Decisão de projeto (V1): fatos, provas, contradições, questões, teses,
riscos, pendências e cronologia vivem como JSONB versionado em
legal_chat_state_versions (snapshot imutável por versão — auditável e
barato). A normalização em tabelas dedicadas fica para a V2, se e quando
houver consulta relacional cruzada entre sessões.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
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

# Status do ciclo de vida da sessão (espelha os filtros da coluna esquerda).
SESSION_STATUS = {
    "em_analise",
    "aguardando_documentos",
    "pronta_para_caso",
    "convertida_em_caso",
    "arquivada",
}

# Modos rápidos de atuação (seletor ao lado do campo de mensagem).
CHAT_MODOS = {
    "conversa_livre",
    "organizar_fatos",
    "analisar_provas",
    "detectar_contradicoes",
    "estrategia_da_parte",
    "simular_defesa",
    "julgar_caso",
    "pesquisar_direito",
    "elaborar_documento",
    "revisar_documento",
}


class LegalChatSession(Base):
    __tablename__ = "legal_chat_sessions"
    __table_args__ = (
        Index("ix_legal_chat_sessions_status_criado", "status", "created_at"),
        Index("ix_legal_chat_sessions_criador_status", "created_by", "status"),
    )

    id = Column(String(36), primary_key=True)
    titulo = Column(String(255), nullable=False)
    status = Column(String(40), nullable=False, default="em_analise", index=True)
    favorita = Column(Boolean, nullable=False, default=False)

    # Identificação preliminar (antes de existir cliente/caso formal).
    cliente_potencial = Column(String(255), nullable=True)
    area_sugerida = Column(String(100), nullable=True)
    advogado_responsavel_id = Column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )

    # Área de trabalho livre (editor): conteúdo + versão de autosave.
    workspace_texto = Column(Text, nullable=True)
    workspace_versao = Column(Integer, nullable=False, default=0)

    # Vínculos pós-conversão / pós-vinculação (nunca obrigatórios).
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True, index=True)
    convertido_case_id = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)
    # Sessão convertida é CONGELADA para auditoria (nenhuma escrita posterior).
    frozen_at = Column(DateTime(timezone=True), nullable=True)

    # Custo acumulado de IA da sessão (denormalizado para a coluna esquerda).
    custo_ia_total = Column(Numeric(12, 6), nullable=False, default=0)

    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    mensagens = relationship(
        "LegalChatMessage",
        back_populates="sessao",
        cascade="all, delete-orphan",
        order_by="LegalChatMessage.created_at",
    )
    anexos = relationship(
        "LegalChatAttachment",
        back_populates="sessao",
        cascade="all, delete-orphan",
        order_by="LegalChatAttachment.created_at",
    )
    estados = relationship(
        "LegalChatStateVersion",
        back_populates="sessao",
        cascade="all, delete-orphan",
        order_by="LegalChatStateVersion.versao",
    )


class LegalChatMessage(Base):
    __tablename__ = "legal_chat_messages"
    __table_args__ = (
        Index("ix_legal_chat_messages_sessao", "session_id", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    session_id = Column(
        String(36),
        ForeignKey("legal_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    autor = Column(String(10), nullable=False)  # "user" | "ia"
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    modo = Column(String(40), nullable=False, default="conversa_livre")
    conteudo = Column(Text, nullable=False)

    # Rastreabilidade da resposta de IA (nulos em mensagens do advogado).
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

    sessao = relationship("LegalChatSession", back_populates="mensagens")


class LegalChatAttachment(Base):
    __tablename__ = "legal_chat_attachments"
    __table_args__ = (
        UniqueConstraint("session_id", "sha256", name="uq_legal_chat_anexo_hash"),
        Index("ix_legal_chat_attachments_sessao", "session_id", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    session_id = Column(
        String(36),
        ForeignKey("legal_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    nome_original = Column(String(255), nullable=False)
    filepath = Column(String(500), nullable=False)
    mimetype = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    tipo_documento = Column(String(100), nullable=True)
    ocr_utilizado = Column(Boolean, nullable=False, default=False)
    # Extração estruturada (partes, datas, valores, pedidos, inconsistências).
    resultado_analise = Column(JSONB, nullable=False, default=dict)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sessao = relationship("LegalChatSession", back_populates="anexos")


class LegalChatStateVersion(Base):
    """Snapshot imutável do estado jurídico consolidado da sessão.

    `estado` (JSONB) segue o contrato:
      fatos[]        {texto, classificacao: comprovado|alegado|inferido|
                      controvertido|ausente|superado, fontes[]}
      provas[]       {nome, origem, trecho, forca, sha256?}
      contradicoes[] {descricao, status: aberta|resolvida}
      questoes[]     {tema, analise}
      teses[]        {tipo: favoravel|contraria|julgador, texto}
      riscos[]       {descricao, nivel: baixo|medio|alto}
      pendencias[]   {descricao, origem: cliente|diligencia}
      cronologia[]   {data, evento, comprovado: bool}
      fontes[]       {titulo, categoria, fonte}
    """

    __tablename__ = "legal_chat_state_versions"
    __table_args__ = (
        UniqueConstraint("session_id", "versao", name="uq_legal_chat_estado_versao"),
        Index("ix_legal_chat_state_sessao", "session_id", "versao"),
    )

    id = Column(String(36), primary_key=True)
    session_id = Column(
        String(36),
        ForeignKey("legal_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    versao = Column(Integer, nullable=False)
    resumo = Column(Text, nullable=True)
    estado = Column(JSONB, nullable=False, default=dict)
    # Autoria da versão: "ia" (pós-resposta) ou "advogado" (edição manual).
    origem = Column(String(20), nullable=False, default="advogado")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sessao = relationship("LegalChatSession", back_populates="estados")
