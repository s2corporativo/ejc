# ── app/models/case_intelligence.py ──────────────────────────────────────────
# FASE 1 do Orquestrador Jurídico — CaseIntelligenceSnapshot.
#
# Fotografia VERSIONADA da inteligência do caso. Hoje a análise vive espalhada
# (triagem em campos do Case, intake/motor de peça em JSON efêmero, Raio-X em
# tabelas próprias); este modelo consolida cada resultado como um snapshot
# imutável e auditável, com versão incremental por caso.
#
# Regras de domínio:
#   • APPEND-ONLY: snapshot nunca é editado nem sobrescrito — novo resultado
#     gera nova versão (padrão audit_log: sem soft delete, histórico íntegro).
#   • HITL (OAB Prov. 205/2021): snapshot automático NUNCA nasce aprovado;
#     `congelado=True` só por ato humano (aprovar_snapshot), que o torna
#     imutável e registra aprovado_por/aprovado_em + AuditLog.
#   • payload é JSONB de estrutura livre mas DOCUMENTADA — chaves esperadas:
#       area              slug canônico de CaseArea (core/taxonomia.py) ou
#                         sentinela "outro"; NUNCA vocabulário fora do canônico
#       fatos             síntese (JÁ sanitizada pelo fluxo de origem — LGPD)
#       teses             {"principal": str, "secundarias": [str]}
#       riscos            pontos fracos / chance de êxito / complexidade
#       provas            provas necessárias ou disponíveis
#       prazos_projetados prazos calculados (nunca Deadline confirmado)
#       peca_sugerida     peça cabível sugerida (código/descrição)
#       checklist         itens bloqueantes {"itens": [...], "pronto": bool}
#       fontes            origem dos dados (ex.: ["ia_triagem", "banco_teses"])
#     O payload nunca contém PII crua além do que o fluxo de origem já produz
#     sanitizado (sanitizar_pii roda ANTES nos fluxos de origem).
from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base

# Origens válidas do snapshot (validadas no service — String no banco para não
# exigir novo tipo enum do Postgres; mudanças futuras ficam aditivas).
ORIGENS_SNAPSHOT: tuple[str, ...] = (
    "triagem", "intake", "raio_x", "motor_peca", "manual", "matriz_teses",
    "orquestrador",  # FASE 5 — LegalCaseOrchestrator (linha do tempo de estados)
    "sala_juridica",  # conversão/vínculo da Sala Jurídica → caso oficial
    # Leitura estratégica de um DOCUMENTO anexado a um caso já existente
    # (analise_estrategica.analisar_caso disparada no upload do GED). Antes
    # desta origem o resultado só existia dentro de AILog.resposta, truncado
    # em 8.000 caracteres e sem nenhuma tela que o lesse — o parecer nascia e
    # morria no log (auditoria de documentos/IA, 2026-08).
    "documento",
)


class CaseIntelligenceSnapshot(Base):
    __tablename__ = "case_intelligence_snapshots"
    __table_args__ = (
        # Versionamento íntegro: uma versão N única por caso (o índice único
        # também blinda contra corrida no max+1 — IntegrityError, nunca
        # sobrescrita silenciosa).
        Index("uq_cis_case_versao", "case_id", "versao", unique=True),
    )

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    versao  = Column(Integer, nullable=False)                # incremental por caso (1, 2, ...)
    origem  = Column(String(20), nullable=False)             # ORIGENS_SNAPSHOT

    payload = Column(JSONB, nullable=False, default=dict)    # estrutura documentada acima
    resumo  = Column(Text, nullable=True)                    # síntese curta legível
    ai_log_ids = Column(JSONB, nullable=False, default=list) # rastreabilidade → AILog

    criado_por = Column(String(36), ForeignKey("users.id"), nullable=True)  # NULL = automático
    criado_em  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # HITL — aprovação humana congela o snapshot (imutável a partir daí)
    congelado    = Column(Boolean, nullable=False, default=False)
    aprovado_por = Column(String(36), ForeignKey("users.id"), nullable=True)
    aprovado_em  = Column(DateTime(timezone=True), nullable=True)
