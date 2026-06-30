# ── app/models/workflow.py ────────────────────────────────────────────────────
# BPM Workflow — templates de etapas processuais configuráveis por área.
from __future__ import annotations
import enum

from sqlalchemy import (
    Column, String, Text, Integer, Boolean,
    DateTime, ForeignKey, Enum as SAEnum, func,
)
from app.core.database import Base


class WorkflowStatus(str, enum.Enum):
    ativo    = "ativo"
    pausado  = "pausado"
    concluido = "concluido"
    cancelado = "cancelado"


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id             = Column(String(36), primary_key=True)
    nome           = Column(String(200), nullable=False)
    descricao      = Column(Text)
    area_juridica  = Column(String(60))
    is_default     = Column(Boolean, nullable=False, default=False)
    created_by     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at     = Column(DateTime(timezone=True), nullable=True)


class WorkflowEtapa(Base):
    __tablename__ = "workflow_etapas"

    id                = Column(String(36), primary_key=True)
    template_id       = Column(String(36), ForeignKey("workflow_templates.id", ondelete="CASCADE"),
                               nullable=False)
    nome              = Column(String(100), nullable=False)
    descricao         = Column(Text)
    ordem             = Column(Integer, nullable=False, default=0)
    sla_dias_uteis    = Column(Integer)          # prazo esperado em dias úteis
    cor               = Column(String(20))       # hex color para UI
    obrigatoria       = Column(Boolean, nullable=False, default=True)
    acao_automatica   = Column(String(50))       # notificar|criar_tarefa|alerta_prazo|nenhuma


class CaseWorkflow(Base):
    __tablename__ = "case_workflows"

    id               = Column(String(36), primary_key=True)
    case_id          = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    template_id      = Column(String(36), ForeignKey("workflow_templates.id", ondelete="RESTRICT"),
                              nullable=False)
    etapa_atual_id   = Column(String(36), ForeignKey("workflow_etapas.id", ondelete="SET NULL"),
                              nullable=True)
    status           = Column(SAEnum(WorkflowStatus, name="workflowstatus"), nullable=False,
                              server_default="ativo")
    iniciado_em      = Column(DateTime(timezone=True), server_default=func.now())
    concluido_em     = Column(DateTime(timezone=True), nullable=True)
    created_by       = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class WorkflowHistorico(Base):
    __tablename__ = "workflow_historico"

    id               = Column(String(36), primary_key=True)
    case_workflow_id = Column(String(36), ForeignKey("case_workflows.id", ondelete="CASCADE"),
                              nullable=False)
    etapa_id         = Column(String(36), ForeignKey("workflow_etapas.id", ondelete="SET NULL"),
                              nullable=True)
    iniciado_em      = Column(DateTime(timezone=True), server_default=func.now())
    concluido_em     = Column(DateTime(timezone=True), nullable=True)
    responsavel_id   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    observacao       = Column(Text)
    sla_respeitado   = Column(Boolean)
