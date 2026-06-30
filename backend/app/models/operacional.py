# ── app/models/operacional.py ─────────────────────────────────────────────────
# Modelos ORM das tabelas que antes existiam SÓ em SQL cru (laudo Fase 5):
#   processes               (baseline 048_processes)
#   pricing_rules           (050_novos_modulos)
#   inadimplencia_alerts    (050_novos_modulos)
#   case_ambiental          (050_novos_modulos)
#   due_diligence_templates (050_novos_modulos)
#   document_access_log     (050_novos_modulos)
#
# Espelham EXATAMENTE o DDL das migrations (tipos, FKs, CHECKs, defaults, índices).
# Não recriam nada em banco existente (create_all usa checkfirst; as migrations
# usam IF NOT EXISTS). Sem relationship() para não alterar os models existentes.
from __future__ import annotations

from sqlalchemy import (
    Column, String, Integer, Boolean, Numeric, Text, Date, DateTime,
    ForeignKey, CheckConstraint, Index, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base

_UUID_DEFAULT = text("gen_random_uuid()::text")


class Process(Base):
    """1 Caso : N Processos (entidade independente do caso)."""
    __tablename__ = "processes"

    id = Column(String(36), primary_key=True, server_default=_UUID_DEFAULT)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    numero_cnj = Column(String(30), nullable=True)
    instancia = Column(String(40), nullable=True)
    tribunal = Column(String(40), nullable=True)
    comarca = Column(String(120), nullable=True)
    vara = Column(String(120), nullable=True)
    classe = Column(String(150), nullable=True)
    fase = Column(String(60), nullable=True)
    tipo = Column(String(40), nullable=False, server_default=text("'judicial'"))
    processo_principal_id = Column(String(36), ForeignKey("processes.id", ondelete="SET NULL"), nullable=True)
    is_principal = Column(Boolean, nullable=False, server_default=text("false"))
    valor_causa = Column(Numeric(14, 2), nullable=True)
    status = Column(String(40), nullable=False, server_default=text("'ativo'"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_processes_case_id", "case_id"),
        Index("ix_processes_principal", "case_id", "is_principal"),
    )


class PricingRule(Base):
    """Motor de precificação OAB (faixas de honorários)."""
    __tablename__ = "pricing_rules"

    id = Column(String(36), primary_key=True, server_default=_UUID_DEFAULT)
    area = Column(String(100), nullable=False)
    case_type = Column(String(150), nullable=False)
    complexity = Column(String(30), nullable=False, server_default=text("'media'"))
    fee_type = Column(String(50), nullable=False, server_default=text("'fixo'"))
    base_amount = Column(Numeric(12, 2), nullable=True)
    percentage_of_value = Column(Numeric(5, 2), nullable=True)
    min_amount = Column(Numeric(12, 2), nullable=True)
    max_amount = Column(Numeric(12, 2), nullable=True)
    exit_percentage = Column(Numeric(5, 2), nullable=True)
    oab_reference = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("complexity IN ('simples','media','alta','muito_alta')", name="pricing_rules_complexity_check"),
        CheckConstraint("fee_type IN ('fixo','percentual','misto','exito')", name="pricing_rules_fee_type_check"),
    )


class InadimplenciaAlert(Base):
    """Controle de inadimplência por honorários."""
    __tablename__ = "inadimplencia_alerts"

    id = Column(String(36), primary_key=True, server_default=_UUID_DEFAULT)
    fee_id = Column(String(36), ForeignKey("fees.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    client_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    days_overdue = Column(Integer, nullable=False, server_default=text("0"))
    amount_due = Column(Numeric(12, 2), nullable=False)
    alert_level = Column(String(30), nullable=False, server_default=text("'leve'"))
    action_taken = Column(Text, nullable=True)
    resolved = Column(Boolean, nullable=False, server_default=text("false"))
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("alert_level IN ('leve','medio','critico','cobranca_formal')", name="inadimplencia_alerts_alert_level_check"),
        Index("ix_inadimplencia_fee_id", "fee_id"),
        Index("ix_inadimplencia_client_id", "client_id"),
        Index("ix_inadimplencia_resolved", "resolved"),
    )


class CaseAmbiental(Base):
    """Módulo Ambiental (IBAMA, CAR, TCFA, carbono) — 1:1 com o caso."""
    __tablename__ = "case_ambiental"

    id = Column(String(36), primary_key=True, server_default=_UUID_DEFAULT)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True)
    subtype = Column(String(80), nullable=True)
    numero_auto = Column(String(100), nullable=True)
    orgao_autuador = Column(String(100), nullable=True)
    data_auto = Column(Date, nullable=True)
    prazo_defesa = Column(Date, nullable=True)
    valor_multa = Column(Numeric(14, 2), nullable=True)
    infracoes = Column(JSONB, nullable=False, server_default=text("'[]'"))
    licenca_tipo = Column(String(80), nullable=True)
    licenca_numero = Column(String(100), nullable=True)
    licenca_validade = Column(Date, nullable=True)
    licenca_orgao = Column(String(100), nullable=True)
    car_numero = Column(String(100), nullable=True)
    reserva_legal_ha = Column(Numeric(10, 4), nullable=True)
    app_area_ha = Column(Numeric(10, 4), nullable=True)
    tcfa_cnpj = Column(String(20), nullable=True)
    tcfa_atividade = Column(String(200), nullable=True)
    tcfa_vencimento = Column(Date, nullable=True)
    tcfa_valor = Column(Numeric(12, 2), nullable=True)
    credito_carbono_ton = Column(Numeric(12, 4), nullable=True)
    observacoes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_case_ambiental_case_id", "case_id"),
    )


class DueDiligenceTemplate(Base):
    """Templates de Due Diligence."""
    __tablename__ = "due_diligence_templates"

    id = Column(String(36), primary_key=True, server_default=_UUID_DEFAULT)
    name = Column(String(200), nullable=False)
    dd_type = Column(String(100), nullable=False)
    items = Column(JSONB, nullable=False, server_default=text("'[]'"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DocumentAccessLog(Base):
    """Log de acesso ao cofre de documentos (LGPD)."""
    __tablename__ = "document_access_log"

    id = Column(String(36), primary_key=True, server_default=_UUID_DEFAULT)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(30), nullable=False, server_default=text("'view'"))
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("action IN ('view','download','print','share','delete')", name="document_access_log_action_check"),
        Index("ix_doc_access_doc_id", "document_id"),
        Index("ix_doc_access_user_id", "user_id"),
        Index("ix_doc_access_created", "created_at"),
    )
