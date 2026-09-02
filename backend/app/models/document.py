# ── app/models/document.py ───────────────────────────────────────────────────
from __future__ import annotations
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import relationship

from app.core.database import Base


class DocConfidencialidade(str, enum.Enum):
    normal       = "normal"
    interno      = "interno"
    restrito     = "restrito"
    confidencial = "confidencial"
    segredo_justica = "segredo_justica"


class Document(Base):
    """GED — documentos enviados (uploads). Cofre = confidencialidade >= restrito."""
    __tablename__ = "documents"

    __table_args__ = (
        # Índice PARCIAL da LISTAGEM (migration 155, AUD27-P3-11). Declarado
        # aqui porque o autogenerate compara índices: sem esta linha ele emite
        # DROP INDEX e uma migration futura desfaz a correção de desempenho em
        # silêncio — nada quebra, só volta a ordenar a tabela inteira para
        # devolver uma página (mesmo modo de falha do #11 em responsavel_id).
        Index("ix_documents_listagem_ativa", text("created_at DESC"),
              postgresql_where=text("deleted_at IS NULL")),
        Index("ix_documents_legal_hold", "legal_hold"),
        Index("ix_documents_retention_until", "retention_until"),
        Index("ix_documents_analysis_status", "analysis_status"),
        Index("ix_documents_malware_scan_status", "malware_scan_status"),
        Index("ix_documents_rag_status", "rag_status"),
    )

    id        = Column(String(36), primary_key=True)
    titulo    = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    tipo      = Column(String(50), nullable=True)   # procuracao|contrato|decisao|peticao|prova|outro

    # Arquivo físico
    filename     = Column(String(255), nullable=False)
    filepath     = Column(String(500), nullable=False)   # caminho no volume uploads
    mimetype     = Column(String(100), nullable=True)
    size_bytes   = Column(Integer, nullable=True)
    # Integridade do arquivo juntado (migration 149). Nullable porque documento
    # anterior à coluna não tem hash — e `NULL` diz isso com honestidade, em vez
    # de fingir integridade que ninguém verificou. O backfill é do rescan.
    sha256       = Column(String(64), nullable=True, index=True)
    ocr_text     = Column(Text, nullable=True)           # texto extraído (busca)

    confidencialidade = Column(
        SAEnum(DocConfidencialidade), nullable=False,
        default=DocConfidencialidade.confidencial, index=True
    )

    case_id   = Column(String(36), ForeignKey("cases.id"),   nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=True, index=True)
    uploaded_by = Column(String(36), nullable=True)

    # Publicação explícita no Portal do Cliente (Issue #698, migration 136).
    # Reclassificar para "normal" NÃO publica sozinho — o Portal exige
    # confidencialidade=normal E publicado_portal=true. Mesmo desenho do
    # Data Room (DataRoomArquivo.publicado_externamente/publicado_por/
    # publicado_em), mas aqui é publicação ao TITULAR autenticado, não link
    # público. publicado_por é NULL quando o próprio cliente é quem enviou o
    # documento pelo Portal (auto-visível ao dono, sem ato do escritório).
    publicado_portal = Column(Boolean, nullable=False, default=False, server_default="false")
    publicado_por     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    publicado_em      = Column(DateTime(timezone=True), nullable=True)

    # Versionamento (G3): histórico de revisões do mesmo documento.
    # versao_grupo_id agrupa todas as versões de um mesmo documento original.
    # versao é o número sequencial (1, 2, 3...); documento vigente = último criado.
    versao             = Column(Integer, nullable=False, server_default="1")
    versao_grupo_id    = Column(String(36), nullable=True, index=True)
    versao_anterior_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Google Drive (quando o doc vive no Drive, não no volume local)
    drive_file_id = Column(String(128), nullable=True, index=True)
    drive_link    = Column(String(500), nullable=True)

    # Governança de ingestão/processamento (migration 156). Campos nullable para
    # não inventar estado de documentos legados; uploads novos os preenchem.
    malware_scan_status = Column(String(20), nullable=True)
    malware_scanned_at = Column(DateTime(timezone=True), nullable=True)
    analysis_status = Column(String(20), nullable=True)
    analysis_updated_at = Column(DateTime(timezone=True), nullable=True)
    analysis_error_code = Column(String(60), nullable=True)
    analysis_source_sha256 = Column(String(64), nullable=True)

    # Retenção / legal hold. Nenhum prazo legal é arbitrado pelo código: o
    # operador jurídico autorizado define retention_until ou legal_hold.
    retention_until = Column(DateTime(timezone=True), nullable=True)
    legal_hold = Column(Boolean, nullable=False, default=False, server_default="false")
    legal_hold_reason = Column(Text, nullable=True)
    legal_hold_set_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    legal_hold_set_at = Column(DateTime(timezone=True), nullable=True)

    # Estado operacional de integridade e ponte GED -> RAG do próprio caso.
    integrity_status = Column(String(20), nullable=True)
    integrity_verified_at = Column(DateTime(timezone=True), nullable=True)
    rag_status = Column(String(20), nullable=True)
    rag_knowledge_doc_id = Column(String(36), nullable=True)
    rag_indexed_at = Column(DateTime(timezone=True), nullable=True)
    rag_source_sha256 = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case   = relationship("Case",   back_populates="documents")
    client = relationship("Client", back_populates="documents")


class DocumentStorageOperation(Base):
    """Outbox durável para eliminação física após hard purge do metadado.

    Não possui FK para ``documents`` deliberadamente: a operação precisa
    sobreviver à exclusão definitiva da linha do GED. O locator fica somente no
    banco operacional e nunca deve ser emitido em logs/respostas públicas.
    """

    __tablename__ = "document_storage_operations"

    id = Column(String(36), primary_key=True)
    # UNIQUE já fornece índice físico no PostgreSQL; não declarar index=True
    # evita criar duas estruturas equivalentes para a mesma chave idempotente.
    operation_key = Column(String(64), nullable=False, unique=True)
    document_id = Column(String(36), nullable=False, index=True)
    storage_kind = Column(String(20), nullable=False)
    storage_locator = Column(String(1000), nullable=False)
    drive_file_id = Column(String(128), nullable=True)
    status = Column(String(20), nullable=False, server_default="pending", index=True)
    attempts = Column(Integer, nullable=False, server_default="0")
    last_error_code = Column(String(60), nullable=True)
    requested_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
