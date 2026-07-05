# ── app/models/prova.py ───────────────────────────────────────────────────────
# Gestão de Provas por CASO — acervo probatório estruturado (gap transversal:
# serve os 8 ramos). Cada prova é CASO-scoped e pode, opcionalmente:
#   • apontar para um Document já no GED do caso (document_id);
#   • vincular-se a uma Tese/pedido que ela sustenta (tese_id);
#   • declarar o `fato_probando` ("o que esta prova prova").
# A ordem (ordem) define a sequência dos anexos no "Documento Único de Anexos".
#
# `tipo` como VARCHAR + validação de domínio no Pydantic (enum TipoProva) — mesmo
# trade-off das demais tabelas raw-SQL do projeto (evita ENUM nativo em migration
# idempotente, ver 071/072).
from __future__ import annotations

import enum

from sqlalchemy import (
    Column, String, Text, Integer, DateTime, ForeignKey, func,
)

from app.core.database import Base


class TipoProva(str, enum.Enum):
    documental  = "documental"
    pericial    = "pericial"
    testemunhal = "testemunhal"
    material    = "material"
    digital     = "digital"
    outro       = "outro"


class Prova(Base):
    """Prova do acervo de um caso (soft delete)."""
    __tablename__ = "provas"

    id            = Column(String(36), primary_key=True)
    case_id       = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    tipo          = Column(String(20), nullable=False, default=TipoProva.documental.value)
    titulo        = Column(String(255), nullable=False)
    descricao     = Column(Text, nullable=True)

    # A prova PODE referenciar um arquivo já existente no GED do caso.
    document_id   = Column(String(36), ForeignKey("documents.id"), nullable=True, index=True)
    # A prova PODE sustentar uma tese/pedido (Banco de Teses institucional).
    tese_id       = Column(String(36), ForeignKey("teses.id"), nullable=True, index=True)

    fato_probando = Column(Text, nullable=True)   # "o que esta prova prova"
    ordem         = Column(Integer, nullable=False, default=0)  # ordem no documento único

    created_by    = Column(String(36), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at    = Column(DateTime(timezone=True), nullable=True)
