# ── app/models/rag.py ────────────────────────────────────────────────────────
# Base de conhecimento RAG: documentos + chunks vetorizados (pgvector).
# Dimensão do embedding = EMBEDDINGS_DIM (default 1024 = multilingual-e5-large); casa com a
# coluna vector(EMBEDDINGS_DIM) da migration 096. Configurável por env.
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, func, Text, Integer, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.core.database import Base
from app.core.config import get_settings


class KnowledgeDoc(Base):
    """Documento ingerido na base de conhecimento (legislação, súmula, peça)."""
    __tablename__ = "knowledge_docs"

    id        = Column(String(36), primary_key=True)
    titulo    = Column(String(500), nullable=False)
    categoria = Column(String(50),  nullable=False, index=True)
    # legislacao | sumula_stf | sumula_stj | sumula_tst | jurisprudencia | precedente_interno | doutrina
    # (peca_escritorio: categoria legada — substituída por precedente_interno na Camada 3)
    fonte     = Column(String(255), nullable=True)   # URL ou referência oficial
    tribunal  = Column(String(20),  nullable=True)
    extra     = Column(JSONB, nullable=True)

    # Isolamento por cliente/caso (Fase 3B / migration 055): conteúdo RESTRITO
    # (peças/precedentes internos) só é recuperável no escopo do próprio cliente.
    # NULL = conteúdo PÚBLICO/global (legislação, súmulas, jurisprudência, doutrina).
    # client_id/case_id são IDENTIFICADORES DE ESCOPO (nem sempre um cliente/caso
    # formal — ex.: escopos sintéticos de teste). O isolamento é imposto na camada
    # de serviço; sem FK estrita para não rejeitar escopos válidos.
    client_id = Column(String(36), nullable=True, index=True)
    case_id   = Column(String(36), nullable=True, index=True)

    # Ingestão automática (migration 006): rastreabilidade + dedup idempotente
    chave_origem  = Column(String(255), nullable=True, index=True)  # URN/nº CNJ/código
    hash_conteudo = Column(String(40),  nullable=True)              # SHA-1 normalizado
    atualizado_em = Column(DateTime(timezone=True), nullable=True)

    # Estado da vetorização (BackgroundTasks): pendente | indexado | sem_embeddings
    status_indexacao = Column(String(20), nullable=False, server_default="pendente")

    # Versionamento (migration 068): reingestão do mesmo `chave_origem` com
    # conteúdo diferente NÃO sobrescreve — cria uma nova versão. A versão
    # antiga vira `vigente=False` mas seus chunks permanecem intactos (histórico
    # auditável; citações antigas usadas em petições continuam rastreáveis).
    versao             = Column(Integer, nullable=False, server_default="1")
    vigente            = Column(Boolean, nullable=False, server_default="true", index=True)
    versao_anterior_id = Column(String(36), ForeignKey("knowledge_docs.id", ondelete="SET NULL"),
                                nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship garante ordem de INSERT (docs antes de chunks) no flush
    chunks = relationship("KnowledgeChunk", back_populates="doc",
                          cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    """Chunk vetorizado para busca semântica."""
    __tablename__ = "knowledge_chunks"

    id          = Column(String(36), primary_key=True)
    doc_id      = Column(String(36), ForeignKey("knowledge_docs.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    conteudo    = Column(Text, nullable=False)
    embedding   = Column(Vector(get_settings().EMBEDDINGS_DIM), nullable=True)  # dim configurável (O-2); casa com migration 096 (default 1024)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    doc = relationship("KnowledgeDoc", back_populates="chunks")


class FonteIngestao(Base):
    """Controle de cada fonte de ingestão automática (1 linha por slug).

    Alimentada pelos jobs do scheduler (BCB, LexML, Câmara/Senado, DataJud,
    STJ CKAN, Querido Diário, IBAMA). Exposta no painel para auditoria:
    quando rodou, status, quantos registros novos/total e último erro.
    """
    __tablename__ = "fontes_ingestao"

    slug            = Column(String(60), primary_key=True)
    descricao       = Column(String(255), nullable=False)
    categoria_rag   = Column(String(50), nullable=True)
    ativo           = Column(Boolean, nullable=False, server_default="true")
    ultima_execucao = Column(DateTime(timezone=True), nullable=True)
    ultimo_status   = Column(String(20), nullable=True)   # sucesso | erro | parcial
    registros_novos = Column(Integer, nullable=False, server_default="0")
    registros_total = Column(Integer, nullable=False, server_default="0")
    ultimo_erro     = Column(Text, nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
