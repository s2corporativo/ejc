# ── app/models/ficha_triagem.py ──────────────────────────────────────────────
# Ficha de Triagem pré-peça — GATE de qualidade da Jornada do Caso.
# Antes de GERAR uma peça, o advogado confirma uma ficha estruturada de triagem
# (competência, rito, legitimidades, prescrição, tutela, provas, valor, risco,
# pedidos). Evita "bom modelo no caso errado": a peça só nasce ancorada numa
# triagem CONFIRMADA (status='confirmada').
#
# Uma ficha CORRENTE por caso (UNIQUE case_id) — o fluxo é UPSERT: pré-preencher
# (IA, rascunho) → advogado edita → confirmar. Mantém-se simples (sem histórico).
#
# `status` e `risco_processual` como VARCHAR com validação de domínio no Pydantic
# (schema/service) — mesmo trade-off das demais tabelas raw-SQL do projeto
# (evita ENUM nativo em migration idempotente, ver models/prova.py 073).
from __future__ import annotations

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class FichaTriagem(Base):
    """Ficha de triagem estruturada, uma corrente por caso (UNIQUE case_id)."""
    __tablename__ = "fichas_triagem"

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False,
                     index=True, unique=True)

    # Enquadramento processual
    competencia           = Column(Text, nullable=True)
    rito                  = Column(Text, nullable=True)
    legitimidade_ativa    = Column(Text, nullable=True)
    legitimidade_passiva  = Column(Text, nullable=True)
    prescricao_decadencia = Column(Text, nullable=True)

    # Tutela de urgência
    tutela_urgencia   = Column(Boolean, nullable=False, default=False)
    tutela_fundamento = Column(Text, nullable=True)

    # Mapa probatório
    provas_disponiveis = Column(Text, nullable=True)
    provas_faltantes   = Column(Text, nullable=True)

    # Valor e risco
    valor_causa      = Column(String(120), nullable=True)
    risco_processual = Column(String(10), nullable=True)   # baixo|medio|alto
    risco_nota       = Column(Text, nullable=True)

    # Pedidos
    pedidos_principais   = Column(Text, nullable=True)
    pedidos_subsidiarios = Column(Text, nullable=True)

    # Confiança 0-100 por campo do pré-preenchimento por IA ({campo: int}).
    confianca = Column(JSONB, nullable=True)

    # rascunho | confirmada — só 'confirmada' abre o gate de geração de peça.
    status = Column(String(20), nullable=False, default="rascunho", index=True)

    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())
