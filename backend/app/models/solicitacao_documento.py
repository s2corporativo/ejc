# ── app/models/solicitacao_documento.py ──────────────────────────────────────
# Solicitação de documentos ao CLIENTE (migration 084).
#
# Fluxo: o advogado cria a solicitação no caso (routers/solicitacoes_documentos)
# com 1..30 itens (opcionalmente vinculados a uma Prova sugerida como faltante);
# o cliente recebe e-mail + sino no Portal e envia cada arquivo pelo Portal do
# Cliente (routers/portal_documentos), que cria um Document no GED do caso e
# marca o item como enviado. Status agregado recalculado a cada upload:
#   pendente (nenhum item enviado) | parcial | atendida (todos enviados).
#
# `status` como VARCHAR com validação de domínio na aplicação — mesmo trade-off
# das demais tabelas raw-SQL do projeto (ver provas/073).
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base

# Domínios (validados na aplicação — colunas VARCHAR)
SOLICITACAO_STATUS = ("pendente", "parcial", "atendida")
ITEM_STATUS = ("pendente", "enviado")


class SolicitacaoDocumento(Base):
    """Pedido formal de documentos ao cliente, escopado a um caso."""
    __tablename__ = "solicitacoes_documentos"

    id        = Column(String(36), primary_key=True)
    case_id   = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    mensagem  = Column(Text, nullable=True)
    status    = Column(String(20), nullable=False, default="pendente")

    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    itens = relationship(
        "SolicitacaoDocumentoItem", back_populates="solicitacao",
        order_by="SolicitacaoDocumentoItem.created_at",
    )


class SolicitacaoDocumentoItem(Base):
    """Um documento pedido dentro da solicitação (1..N)."""
    __tablename__ = "solicitacao_documento_itens"

    id             = Column(String(36), primary_key=True)
    solicitacao_id = Column(String(36), ForeignKey("solicitacoes_documentos.id"),
                            nullable=False, index=True)
    # Vínculo opcional com a Prova (ex.: sugerida como faltante pela IA).
    prova_id       = Column(String(36), ForeignKey("provas.id"), nullable=True)
    nome           = Column(String(255), nullable=False)
    descricao      = Column(Text, nullable=True)
    status         = Column(String(20), nullable=False, default="pendente")
    # Preenchidos quando o cliente envia o arquivo pelo Portal.
    documento_id   = Column(String(36), ForeignKey("documents.id"), nullable=True)
    enviado_em     = Column(DateTime(timezone=True), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    solicitacao = relationship("SolicitacaoDocumento", back_populates="itens")
