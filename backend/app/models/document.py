# ── app/models/document.py ───────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, Text, Integer, ForeignKey, Boolean, Index, text
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


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
        # Índice PARCIAL da LISTAGEM (migration 154, AUD27-P3-11). Declarado
        # aqui porque o autogenerate compara índices: sem esta linha ele emite
        # DROP INDEX e uma migration futura desfaz a correção de desempenho em
        # silêncio — nada quebra, só volta a ordenar a tabela inteira para
        # devolver uma página (mesmo modo de falha do #11 em responsavel_id).
        Index("ix_documents_listagem_ativa", text("created_at DESC"),
              postgresql_where=text("deleted_at IS NULL")),
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
    # Integridade do arquivo juntado (migration 147). Nullable porque documento
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

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case   = relationship("Case",   back_populates="documents")
    client = relationship("Client", back_populates="documents")
