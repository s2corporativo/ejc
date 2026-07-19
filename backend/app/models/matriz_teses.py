# ── app/models/matriz_teses.py ───────────────────────────────────────────────
# FASE 3 do Orquestrador Jurídico — Matriz de Teses estruturada.
#
# Hoje as teses vivem como TEXTO (Case.tese_principal, banco de Teses, prosa da
# IA). Estas tabelas estruturam a matriz tese × fato × prova × precedente:
#
#   • LegalIssue       — questão jurídica decomposta do caso (competência,
#                        prescrição, legitimidade, mérito, dano, prova, tutela…),
#                        origem "ia" (decomposição automática) ou "manual".
#   • ThesisCandidate  — tese candidata da matriz. NASCE SEMPRE status
#                        "candidata" (HITL): aprovação/descarte é ato humano de
#                        advogado+ com AuditLog. `forca` é score DETERMINÍSTICO
#                        (ver matriz_teses_service.calcular_forca) — NUNCA nota
#                        dada por LLM.
#   • AuthorityRecord  — precedente/autoridade REAL: só nasce de retorno do
#                        RAG/verificador com trecho e referência (nunca
#                        inventado). status_verificacao="verificada" EXIGE
#                        fonte_oficial (validado no service).
#   • EvidenceLink     — vínculo fato × prova × tese (× pedido) da matriz.
#
# Tipos String + validação de domínio no service (mesmo trade-off de prova.py /
# case_intelligence.py: sem ENUM nativo do Postgres — mudanças ficam aditivas).
from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base

# Domínios validados no service (String no banco — aditivo).
ORIGENS_ISSUE: tuple[str, ...] = ("ia", "manual")
STATUS_TESE: tuple[str, ...] = ("candidata", "aprovada", "descartada")
STATUS_VERIFICACAO: tuple[str, ...] = ("nao_verificada", "verificada", "nao_encontrada")


class LegalIssue(Base):
    """Questão jurídica decomposta de um caso (unidade de pesquisa da matriz)."""
    __tablename__ = "legal_issues"

    id         = Column(String(36), primary_key=True)
    case_id    = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    questao    = Column(Text, nullable=False)          # ex.: "Há prescrição quinquenal?"
    area       = Column(String(60), nullable=True)     # slug canônico (core/taxonomia.py)
    prioridade = Column(Integer, nullable=False, default=3)  # 1 (alta) … 5 (baixa)
    origem     = Column(String(10), nullable=False, default="ia")  # ORIGENS_ISSUE

    criado_por = Column(String(36), ForeignKey("users.id"), nullable=True)
    criado_em  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ThesisCandidate(Base):
    """Tese candidata da matriz — rascunho até aprovação humana (HITL)."""
    __tablename__ = "thesis_candidates"

    id       = Column(String(36), primary_key=True)
    case_id  = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    issue_id = Column(String(36), ForeignKey("legal_issues.id"), nullable=True)

    tese       = Column(Text, nullable=False)
    fundamento = Column(Text, nullable=True)           # artigos/súmulas/princípios

    # Estrutura da matriz (JSONB — listas):
    #   fatos_relacionados: ["<fato>", ...]
    #   provas:             ["<prova_id ou descrição>", ...]
    #   precedentes:        [{"authority_id","tribunal","processo_ref",
    #                         "status_verificacao","favoravel","fonte_oficial"}, ...]
    #   vulnerabilidades:   ["<fragilidade/contra-argumento>", ...]
    fatos_relacionados = Column(JSONB, nullable=False, default=list)
    provas             = Column(JSONB, nullable=False, default=list)
    precedentes        = Column(JSONB, nullable=False, default=list)
    vulnerabilidades   = Column(JSONB, nullable=False, default=list)

    # Score DETERMINÍSTICO 0-100 (matriz_teses_service.calcular_forca) — nunca LLM.
    forca  = Column(Integer, nullable=False, default=0)
    status = Column(String(15), nullable=False, default="candidata")  # STATUS_TESE

    criado_por   = Column(String(36), ForeignKey("users.id"), nullable=True)
    criado_em    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # HITL — só ato humano preenche (aprovada OU descartada, com AuditLog).
    aprovado_por = Column(String(36), ForeignKey("users.id"), nullable=True)
    aprovado_em  = Column(DateTime(timezone=True), nullable=True)


class AuthorityRecord(Base):
    """Precedente/autoridade com origem REAL (RAG/verificador) — nunca inventado.

    Invariante (validada no service): status_verificacao="verificada" ⇒
    fonte_oficial preenchida. `favoravel` é heurística DETERMINÍSTICA por
    metadados (None = indefinido) — nunca rótulo de LLM nesta fase.
    """
    __tablename__ = "authority_records"

    id           = Column(String(36), primary_key=True)
    case_id      = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    tribunal     = Column(String(60), nullable=True)
    processo_ref = Column(String(120), nullable=True)   # nº CNJ / REsp / súmula / doc RAG
    orgao        = Column(String(120), nullable=True)
    data_julgamento = Column(String(40), nullable=True)  # texto extraído ("12/03/2024")
    tema         = Column(String(300), nullable=True)    # questão que motivou a busca
    trecho       = Column(Text, nullable=False)          # trecho REAL retornado (obrigatório)
    fonte_oficial = Column(String(500), nullable=True)   # obrigatória quando "verificada"
    status_verificacao = Column(String(20), nullable=False,
                                default="nao_verificada")  # STATUS_VERIFICACAO
    favoravel    = Column(Boolean, nullable=True)        # None = indefinido

    criado_em    = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EvidenceLink(Base):
    """Vínculo fato × prova × tese (× pedido) da matriz."""
    __tablename__ = "evidence_links"

    id       = Column(String(36), primary_key=True)
    case_id  = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    fato     = Column(Text, nullable=False)             # texto do fato (ou ref)
    prova_id = Column(String(36), ForeignKey("provas.id"), nullable=True)
    tese_id  = Column(String(36), ForeignKey("thesis_candidates.id"), nullable=True)
    pedido   = Column(Text, nullable=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
