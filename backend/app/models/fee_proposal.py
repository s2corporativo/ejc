# ── app/models/fee_proposal.py ───────────────────────────────────────────────
# FASE 4 do Orquestrador Jurídico — Proposta de Honorários versionada (HITL).
#
# NÃO confundir com models/fee.py (Fee = lançamento FINANCEIRO de honorário já
# contratado). FeeProposal é a PROPOSTA comercial pré-contrato, ancorada na
# tabela OAB/MG estruturada (TabelaOABHonorario):
#
#   • faixas {minimo_etico, recomendado, estrategico} — cada uma com `valor` e
#     `memoria_calculo`. O mínimo ético vem VERBATIM do item OAB vigente; as
#     demais são multiplicadores FIXOS documentados no service
#     (fee_proposal_service) — NUNCA valor definido por LLM, NUNCA inventado.
#   • origem_tabela — item OAB verbatim + fonte + vigência (ou null quando não
#     há item aplicável: "sem base OAB — não preencher automaticamente").
#
# REGRA DE IMUTABILIDADE: proposta APROVADA é IMUTÁVEL. Qualquer mudança gera
# NOVA versão (versao = max+1 por caso); ao aprovar uma nova, as aprovadas
# anteriores do caso viram "substituida" (service.aprovar). Aprovação/rejeição
# são atos humanos de advogado+ com AuditLog obrigatório.
#
# Tipos String + validação de domínio no service (mesmo trade-off de
# matriz_teses.py / prova.py: sem ENUM nativo — mudanças ficam aditivas).
from __future__ import annotations

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base

# Domínio validado no service (String no banco — aditivo).
STATUS_PROPOSTA: tuple[str, ...] = ("rascunho", "aprovada", "rejeitada", "substituida")


class FeeProposal(Base):
    """Proposta de honorários de um caso — versionada e imutável após aprovação."""
    __tablename__ = "fee_proposals"
    __table_args__ = (
        # Uma versão por caso — versionamento estrito (nunca sobrescrever).
        Index("uq_fee_proposals_case_versao", "case_id", "versao", unique=True),
    )

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    versao  = Column(Integer, nullable=False)              # incremental por caso (max+1)
    status  = Column(String(15), nullable=False, default="rascunho")  # STATUS_PROPOSTA

    # Item OAB VERBATIM (item_codigo, descricao, valor_minimo, percentual,
    # unidade, vigencia_inicio/fim, fonte) — ou None quando sem item aplicável.
    origem_tabela = Column(JSONB, nullable=True)

    # {"minimo_etico": {"valor", "memoria_calculo"},
    #  "recomendado":  {"valor", "memoria_calculo"},
    #  "estrategico":  {"valor", "memoria_calculo"}}
    faixas = Column(JSONB, nullable=False, default=dict)

    exito_percentual  = Column(Numeric(5, 2), nullable=True)  # % sobre proveito econômico
    # {"descricao"} ou {"entrada", "num_parcelas", "valor_parcela"} — livre/estruturado.
    parcelamento      = Column(JSONB, nullable=True)
    despesas_criterio = Column(Text, nullable=True)           # critério de custas/despesas
    justificativa     = Column(Text, nullable=True)           # motivação do advogado

    criado_por = Column(String(36), ForeignKey("users.id"), nullable=True)
    criado_em  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # HITL — só o ato humano de aprovação (advogado+) preenche; congela a proposta.
    aprovado_por = Column(String(36), ForeignKey("users.id"), nullable=True)
    aprovado_em  = Column(DateTime(timezone=True), nullable=True)
