# ── app/models/redesign.py ────────────────────────────────────────────────────
# Tabelas de configuração/master data do redesign EJC (migração 057):
#   ModuleHelp         — ajuda contextual por módulo, editável sem redeploy.
#   AreaModuloMapping  — matriz área do direito → módulos/ferramentas.
#   DocumentTypeMaster — tipos de documento para importação/classificação.
#   TabelaOABHonorario — referência OAB/MG versionada por vigência.
from __future__ import annotations

from sqlalchemy import (
    Column, String, Text, Integer, Boolean, Date, Numeric,
    DateTime, ForeignKey, UniqueConstraint, Index, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class ModuleHelp(Base):
    """Ajuda contextual por módulo (botão "?" por tela — F4/R1).

    `module_key` corresponde à rota do frontend sem a barra inicial
    (ex.: "casos", "prazos", "documentos", "ramos/civel"). Vários blocos por
    módulo são permitidos, ordenados por `ordem`.
    """
    __tablename__ = "module_help"

    id             = Column(String(36), primary_key=True)
    module_key     = Column(String(60), nullable=False, index=True)
    titulo         = Column(String(200), nullable=False)
    conteudo_md    = Column(Text, nullable=False)   # markdown: o que faz, quando usar, passo a passo…
    ordem          = Column(Integer, nullable=False, default=0)
    ativo          = Column(Boolean, nullable=False, default=True)
    atualizado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AreaModuloMapping(Base):
    """Matriz área do direito → módulos/ferramentas (R6 — antes hardcoded).

    `area_juridica` em slug minúsculo (ex.: "civel", "familia", "administrativo").
    `module_key` = rota do frontend (ex.: "casos", "ramos/penal").
    `ferramentas` = lista JSON de {"nome", "endpoint"} com endpoints REAIS da
    API (relativos ao prefixo /api — ex.: "/civel/ferramentas/prazos-contestacao").
    """
    __tablename__ = "area_modulos_mapping"
    __table_args__ = (
        UniqueConstraint("area_juridica", "module_key", name="uq_area_modulos_area_module"),
    )

    id                    = Column(String(36), primary_key=True)
    area_juridica         = Column(String(50), nullable=False, index=True)
    module_key            = Column(String(60), nullable=False)
    habilitado            = Column(Boolean, nullable=False, default=True)
    ordem                 = Column(Integer, nullable=False, default=0)
    ferramentas           = Column(JSONB, nullable=True)
    workflow_template_id  = Column(String(36), ForeignKey("workflow_templates.id",  ondelete="SET NULL"), nullable=True)
    checklist_template_id = Column(String(36), ForeignKey("checklist_templates.id", ondelete="SET NULL"), nullable=True)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DocumentTypeMaster(Base):
    """Tipos de documento para importação/classificação (B5/R3).

    `campos_extracao` = schema JSON dos campos específicos que a extração IA
    deve preencher para o tipo (ex.: nfe_xml → chave_acesso, ncm…).
    `categoria`: juridico | fiscal | administrativo | pessoal | outro
    (CHECK no banco — migração 057).
    """
    __tablename__ = "document_types_master"

    id                = Column(String(36), primary_key=True)
    tipo_key          = Column(String(50), nullable=False, unique=True)   # slug
    nome              = Column(String(120), nullable=False)
    descricao         = Column(Text, nullable=True)
    categoria         = Column(String(50), nullable=False, default="outro")
    campos_extracao   = Column(JSONB, nullable=True)
    extensoes_aceitas = Column(JSONB, nullable=True)
    ativo             = Column(Boolean, nullable=False, default=True)
    ordem             = Column(Integer, nullable=False, default=0)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TabelaOABHonorario(Base):
    """Item da Tabela de Honorários OAB/MG, versionado por vigência (R5).

    REGRA (CLAUDE.md): nunca inventar valores — `fonte` é NOT NULL e deve
    citar o documento/URL oficial da OAB/MG. Nova vigência = novos registros
    (fechar `vigencia_fim` dos antigos), nunca sobrescrever.
    """
    __tablename__ = "tabela_oab_honorarios"
    __table_args__ = (
        Index("ix_tabela_oab_honorarios_area_ativo", "area_juridica", "ativo"),
    )

    id              = Column(String(36), primary_key=True)
    item_codigo     = Column(String(30), nullable=False)
    descricao       = Column(String(300), nullable=False)
    area_juridica   = Column(String(50), nullable=True)
    valor_minimo    = Column(Numeric(12, 2), nullable=True)
    percentual      = Column(Numeric(5, 2), nullable=True)
    unidade         = Column(String(30), nullable=True)   # ex.: "R$", "% valor da causa", "URH"
    vigencia_inicio = Column(Date, nullable=True)   # pode ser desconhecida na importação (documentada em `fonte`)
    vigencia_fim    = Column(Date, nullable=True)
    fonte           = Column(String(300), nullable=False)  # URL/documento oficial OAB/MG
    observacoes     = Column(Text, nullable=True)
    ativo           = Column(Boolean, nullable=False, default=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
