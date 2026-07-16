# ── app/models/case.py ────────────────────────────────────────────────────────
from __future__ import annotations
import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class CaseArea(str, enum.Enum):
    # Valores originais (migration 001)
    civil = "civil"
    trabalhista = "trabalhista"
    consumidor = "consumidor"
    familia = "familia"
    ambiental = "ambiental"
    criminal = "criminal"
    previdenciario = "previdenciario"
    empresarial = "empresarial"
    tributario = "tributario"
    # Ramos adicionais (migration 083)
    administrativo = "administrativo"
    bancario = "bancario"
    imobiliario = "imobiliario"
    sucessoes = "sucessoes"
    constitucional = "constitucional"
    digital_lgpd = "digital_lgpd"
    transito = "transito"
    # Expansão da taxonomia canônica (migration 094)
    saude = "saude"
    medico = "medico"
    agrario = "agrario"
    agronegocio = "agronegocio"
    eleitoral = "eleitoral"
    internacional = "internacional"
    contratual = "contratual"
    societario = "societario"
    licitacoes = "licitacoes"


class CaseStatus(str, enum.Enum):
    triagem = "triagem"
    ativo = "ativo"
    suspenso = "suspenso"
    acordo = "acordo"
    encerrado = "encerrado"
    arquivado = "arquivado"


class CaseFase(str, enum.Enum):
    pre_processual = "pre_processual"
    conhecimento = "conhecimento"
    recursal = "recursal"
    execucao = "execucao"
    administrativo = "administrativo"


class CasePrioridade(str, enum.Enum):
    baixa = "baixa"
    media = "media"
    alta = "alta"
    critica = "critica"


class Case(Base):
    __tablename__ = "cases"

    # Unicidade de numero_interno via ÍNDICE ÚNICO PARCIAL (migration 075): só
    # entre casos ATIVOS (deleted_at IS NULL). numero_interno NÃO usa unique=True.
    __table_args__ = (
        Index(
            "uq_cases_numero_interno_active",
            "numero_interno",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id = Column(String(36), primary_key=True)
    numero_interno = Column(String(20), index=True)  # DPT-2026-0001
    titulo = Column(String(255), nullable=False)
    area = Column(SAEnum(CaseArea), nullable=False, index=True)
    status = Column(SAEnum(CaseStatus), nullable=False, default=CaseStatus.triagem, index=True)
    fase = Column(SAEnum(CaseFase), nullable=False, default=CaseFase.pre_processual)
    prioridade = Column(SAEnum(CasePrioridade), nullable=False, default=CasePrioridade.media)
    risco = Column(String(20), nullable=True)  # baixo | medio | alto

    # Processo judicial
    numero_processo = Column(String(30), nullable=True, index=True)
    tribunal = Column(String(20), nullable=True)
    comarca = Column(String(100), nullable=True)
    vara = Column(String(100), nullable=True)
    drive_folder_id = Column(String(128), nullable=True)
    parte_contraria = Column(String(255), nullable=True)
    valor_causa = Column(Numeric(14, 2), nullable=True)

    # Auditoria e Sincronização (DataJud/PJe)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    sync_pending = Column(Boolean, default=False)
    sync_error = Column(Text, nullable=True)
    datajud_ultimo_andamento_em = Column(DateTime(timezone=True), nullable=True)

    # Tipo de caso (núcleo Casos&Processos)
    case_type = Column(String(50), nullable=True, default="judicial")
    extrajudicial_type = Column(String(50), nullable=True)
    has_judicial_process = Column(Boolean, default=False)
    kanban_column = Column(String(100), nullable=True)
    kanban_position = Column(Integer, nullable=True)
    linked_judicial_case_id = Column(String(36), nullable=True)

    # Estratégia (área restrita por perfil)
    descricao_fatos = Column(Text, nullable=True)
    tese_principal = Column(Text, nullable=True)
    pontos_fortes = Column(Text, nullable=True)
    pontos_fracos = Column(Text, nullable=True)
    observacoes = Column(Text, nullable=True)

    # Prescrição
    tipo_acao_prescricao = Column(String(100), nullable=True)
    data_prescricao = Column(DateTime(timezone=True), nullable=True)
    causa_interruptiva = Column(String(255), nullable=True)

    # Responsáveis
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    advogado_responsavel_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    advogado_auxiliar_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    data_encerramento = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archive_reason = Column(Text, nullable=True)
    resultado = Column(String(50), nullable=True)
    motivo_resultado = Column(Text, nullable=True)
    provas_determinantes = Column(Text, nullable=True)
    licoes_aprendidas = Column(Text, nullable=True)

    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    client = relationship("Client", back_populates="cases")
    advogado_responsavel = relationship("User", foreign_keys=[advogado_responsavel_id])
    advogado_auxiliar = relationship("User", foreign_keys=[advogado_auxiliar_id])
    documentos = relationship("Document", back_populates="case")
    prazos = relationship("Deadline", back_populates="case")
    tarefas = relationship("Task", back_populates="case")
    movimentos = relationship("CaseMovimento", back_populates="case", cascade="all, delete-orphan")


class CaseMovimento(Base):
    __tablename__ = "case_movimentos"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    tipo = Column(String(50), nullable=False, default="nota")
    descricao = Column(Text, nullable=False)
    resumo_ia = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    case = relationship("Case", back_populates="movimentos")
