# -- app/models/checklist.py --
from __future__ import annotations
import enum
from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey, Enum as SAEnum, func
from sqlalchemy.orm import relationship
from app.core.database import Base

class ChecklistItemCategoria(str, enum.Enum):
    documentos  = "documentos"
    diligencias = "diligencias"
    prazos      = "prazos"
    audiencia   = "audiencia"
    financeiro  = "financeiro"
    comunicacao = "comunicacao"
    outros      = "outros"

class ChecklistStatus(str, enum.Enum):
    em_andamento = "em_andamento"
    concluido    = "concluido"
    cancelado    = "cancelado"

class ChecklistTemplate(Base):
    __tablename__ = "checklist_templates"
    id              = Column(String(36), primary_key=True)
    nome            = Column(String(200), nullable=False)
    descricao       = Column(Text)
    area_juridica   = Column(String(60))
    fase_processual = Column(String(80))
    tags            = Column(Text)
    is_default      = Column(Boolean, nullable=False, default=False)
    created_by      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at      = Column(DateTime(timezone=True), nullable=True)

    # viewonly: usado só para selectinload (leitura); a escrita de itens
    # continua manual via db.add no router — nada muda no fluxo de gravação.
    itens = relationship(
        "ChecklistTemplateItem",
        primaryjoin="ChecklistTemplate.id == ChecklistTemplateItem.template_id",
        order_by="ChecklistTemplateItem.ordem",
        viewonly=True, lazy="select",
    )

class ChecklistTemplateItem(Base):
    __tablename__ = "checklist_template_items"
    id          = Column(String(36), primary_key=True)
    template_id = Column(String(36), ForeignKey("checklist_templates.id", ondelete="CASCADE"), nullable=False)
    texto       = Column(String(500), nullable=False)
    dica        = Column(Text)
    categoria   = Column(SAEnum(ChecklistItemCategoria, name="checklistitemcategoria"), nullable=False, default=ChecklistItemCategoria.outros)
    obrigatorio = Column(Boolean, nullable=False, default=True)
    ordem       = Column(Integer, nullable=False, default=0)

class CaseChecklist(Base):
    __tablename__ = "case_checklists"
    id          = Column(String(36), primary_key=True)
    case_id     = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(String(36), ForeignKey("checklist_templates.id", ondelete="SET NULL"), nullable=True)
    nome        = Column(String(200), nullable=False)
    status      = Column(SAEnum(ChecklistStatus, name="checkliststatus"), nullable=False, default=ChecklistStatus.em_andamento)
    total_itens = Column(Integer, nullable=False, default=0)
    itens_ok    = Column(Integer, nullable=False, default=0)
    created_by  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # viewonly: habilita selectinload (leitura); escrita permanece manual.
    itens = relationship(
        "CaseChecklistItem",
        primaryjoin="CaseChecklist.id == CaseChecklistItem.case_checklist_id",
        order_by="CaseChecklistItem.ordem",
        viewonly=True, lazy="select",
    )

class CaseChecklistItem(Base):
    __tablename__ = "case_checklist_items"
    id                = Column(String(36), primary_key=True)
    case_checklist_id = Column(String(36), ForeignKey("case_checklists.id", ondelete="CASCADE"), nullable=False)
    template_item_id  = Column(String(36), ForeignKey("checklist_template_items.id", ondelete="SET NULL"), nullable=True)
    texto             = Column(String(500), nullable=False)
    dica              = Column(Text)
    categoria         = Column(SAEnum(ChecklistItemCategoria, name="checklistitemcategoria"), nullable=False, default=ChecklistItemCategoria.outros)
    obrigatorio  = Column(Boolean, nullable=False, default=True)
    ordem        = Column(Integer, nullable=False, default=0)
    concluido    = Column(Boolean, nullable=False, default=False)
    concluido_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    concluido_em  = Column(DateTime(timezone=True), nullable=True)
    observacao   = Column(Text)
