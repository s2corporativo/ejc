# ── app/models/case.py ────────────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, Text, Numeric, ForeignKey, Boolean, Integer, Index, text
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class CaseArea(str, enum.Enum):
    # Valores originais (migration 001)
    civil         = "civil"
    trabalhista   = "trabalhista"
    consumidor    = "consumidor"
    familia       = "familia"
    ambiental     = "ambiental"
    criminal      = "criminal"
    previdenciario = "previdenciario"
    empresarial   = "empresarial"
    tributario    = "tributario"
    # Ramos adicionais alinhados ao frontend e à tabela canônica `areas`
    # (migration 083).
    administrativo = "administrativo"
    bancario      = "bancario"
    imobiliario   = "imobiliario"
    sucessoes     = "sucessoes"
    constitucional = "constitucional"
    digital_lgpd  = "digital_lgpd"
    transito      = "transito"
    # Expansão canônica para áreas já utilizadas pelos fluxos do EJC
    # (migration 094).
    saude         = "saude"
    medico        = "medico"
    agrario       = "agrario"
    agronegocio   = "agronegocio"
    eleitoral     = "eleitoral"
    internacional = "internacional"
    contratual    = "contratual"
    societario    = "societario"
    licitacoes    = "licitacoes"


class CaseStatus(str, enum.Enum):
    triagem    = "triagem"
    ativo      = "ativo"
    suspenso   = "suspenso"
    acordo     = "acordo"
    encerrado  = "encerrado"
    arquivado  = "arquivado"


class CaseFase(str, enum.Enum):
    pre_processual = "pre_processual"
    conhecimento   = "conhecimento"
    recursal       = "recursal"
    execucao       = "execucao"
    administrativo = "administrativo"


class CasePrioridade(str, enum.Enum):
    baixa   = "baixa"
    media   = "media"
    alta    = "alta"
    critica = "critica"


# ============================================================================
# RECOMENDAÇÃO 2: Estados operacionais padronizados para casos ativos
# ============================================================================
class CaseOperationalStatus(str, enum.Enum):
    """
    Estados operacionais padronizados para casos ativos.
    Evita que usuários escrevam livremente o status.
    """
    onboarding = "onboarding"              # Caso recém-criado, em onboarding
    planejamento = "planejamento"          # Em planejamento estratégico
    aguardando_cliente = "aguardando_cliente"  # Aguardando ação/documento do cliente
    aguardando_terceiro = "aguardando_terceiro"  # Aguardando terceiro (tribunal, órgão público)
    em_andamento = "em_andamento"          # Caso em andamento normal
    providencia_urgente = "providencia_urgente"  # Requer ação urgente
    negociacao = "negociacao"              # Em fase de negociação
    encerramento = "encerramento"          # Em fase de encerramento
    encerrado = "encerrado"                # Caso encerrado


class Case(Base):
    __tablename__ = "cases"

    # Unicidade de numero_interno via ÍNDICE ÚNICO PARCIAL (migration 075): só
    # entre casos ATIVOS (deleted_at IS NULL). numero_interno NÃO usa unique=True.
    __table_args__ = (
        Index("uq_cases_numero_interno_active", "numero_interno", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )

    id        = Column(String(36), primary_key=True)
    numero_interno = Column(String(20), index=True)  # DPT-2026-0001
    titulo    = Column(String(255), nullable=False)
    area      = Column(SAEnum(CaseArea), nullable=False, default=CaseArea.civil, index=True)
    status    = Column(SAEnum(CaseStatus), nullable=False, default=CaseStatus.triagem, index=True)
    fase      = Column(SAEnum(CaseFase), nullable=False, default=CaseFase.pre_processual)
    prioridade = Column(SAEnum(CasePrioridade), nullable=False, default=CasePrioridade.media)
    risco     = Column(String(20), nullable=True)   # baixo | medio | alto
    
    # =========================================================================
    # RECOMENDAÇÃO 2: Próxima ação obrigatória em todo caso ativo
    # =========================================================================
    operacional_status = Column(
        SAEnum(CaseOperationalStatus),
        nullable=True,
        default=CaseOperationalStatus.onboarding,
        index=True
    )
    proxima_acao = Column(Text, nullable=True)  # Descrição da próxima ação necessária
    responsavel_proxima_acao_id = Column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    data_esperada_proxima_acao = Column(DateTime(timezone=True), nullable=True)
    urgencia_proxima_acao = Column(
        SAEnum(CasePrioridade), nullable=True
    )  # baixa, media, alta, critica
    bloqueio_descricao = Column(Text, nullable=True)  # Se há bloqueio, descrevê-lo
    documento_origem_acao = Column(String(36), ForeignKey("documents.id"), nullable=True)
    evento_origem_acao = Column(String(36), ForeignKey("case_movimentos.id"), nullable=True)
    # =========================================================================

    # Processo judicial
    numero_processo = Column(String(30), nullable=True, index=True)
    tribunal  = Column(String(20),  nullable=True)
    comarca   = Column(String(100), nullable=True)
    vara      = Column(String(100), nullable=True)
    drive_folder_id = Column(String(128), nullable=True)  # subpasta do caso no Google Drive
    parte_contraria = Column(String(255), nullable=True)
    valor_causa = Column(Numeric(14, 2), nullable=True)

    # Auditoria e Sincronização (DataJud/PJe)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    sync_pending   = Column(Boolean, default=False)
    sync_error     = Column(Text, nullable=True)
    # Marcador explícito do último andamento oficial visto pelo sync diário
    # com notificação ao cliente (migration 084 / datajud_sync_service).
    datajud_ultimo_andamento_em = Column(DateTime(timezone=True), nullable=True)

    # Tipo de caso (núcleo Casos&Processos)
    case_type           = Column(String(50), nullable=True, default="judicial")
    extrajudicial_type  = Column(String(50), nullable=True)
    has_judicial_process = Column(Boolean, default=False)
    kanban_column       = Column(String(100), nullable=True)
    kanban_position     = Column(Integer, nullable=True)
    linked_judicial_case_id = Column(String(36), nullable=True)

    # Estratégia (área restrita por perfil)
    descricao_fatos = Column(Text, nullable=True)
    tese_principal  = Column(Text, nullable=True)
    pontos_fortes   = Column(Text, nullable=True)
    pontos_fracos   = Column(Text, nullable=True)
    observacoes     = Column(Text, nullable=True)

    # Prescrição
    tipo_acao_prescricao = Column(String(100), nullable=True)
    data_prescricao      = Column(DateTime(timezone=True), nullable=True)
    causa_interruptiva   = Column(String(255), nullable=True)

    # Responsáveis
    client_id  = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    advogado_responsavel_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    # index=True declara o ix_cases_advogado_auxiliar_id da migration 076 (#11)
    advogado_auxiliar_id    = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    data_encerramento = Column(DateTime(timezone=True), nullable=True)
    archived_at       = Column(DateTime(timezone=True), nullable=True)
    archive_reason    = Column(Text, nullable=True)
    resultado         = Column(String(50), nullable=True)  # exito_total|exito_parcial|acordo|improcedente
    # Pós-Mortem Jurídico (ECJ): cada caso encerrado vira aprendizado institucional
    motivo_resultado     = Column(Text, nullable=True)
    provas_determinantes = Column(Text, nullable=True)
    licoes_aprendidas    = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relacionamentos
    client     = relationship("Client", back_populates="cases")
    advogado_responsavel = relationship("User", foreign_keys=[advogado_responsavel_id], back_populates="cases_responsible")
    deadlines  = relationship("Deadline",  back_populates="case")
    documents  = relationship("Document",  back_populates="case")
    legal_docs = relationship("LegalDoc",  back_populates="case")
    fees       = relationship("Fee",       back_populates="case")
    movimentos = relationship("CaseMovimento", back_populates="case", order_by="CaseMovimento.created_at.desc()")
    partes     = relationship("CaseParte", back_populates="case", cascade="all, delete-orphan")
    areas      = relationship("CasoArea",  back_populates="case", cascade="all, delete-orphan")
    environmental = relationship("EnvironmentalCase", back_populates="case", uselist=False)
    empresarial   = relationship("EmpresarialCase",   back_populates="case", uselist=False)
    civel         = relationship("CivelCase",          back_populates="case", uselist=False)
    penal         = relationship("PenalCase",          back_populates="case", uselist=False)
    trabalhista_esp = relationship("TrabalhistaCase",  back_populates="case", uselist=False)
    admin_esp     = relationship("AdminCase",          back_populates="case", uselist=False)
    bancario      = relationship("BancarioCase",       back_populates="case", uselist=False)
    
    # Relacionamentos das novas fields de próxima ação
    responsavel_proxima_acao = relationship(
        "User", foreign_keys=[responsavel_proxima_acao_id], back_populates="assigned_actions"
    )
    doc_origem_acao = relationship("Document", foreign_keys=[documento_origem_acao])
    evento_origem = relationship("CaseMovimento", foreign_keys=[evento_origem_acao])


class CaseMovimentoTipo(str, enum.Enum):
    """Tipos padronizados de eventos na timeline do caso."""
    peticao = "peticao"
    decisao = "decisao"
    audiencia = "audiencia"
    nota = "nota"
    intimacao = "intimacao"
    ia = "ia"
    documento_recebido = "documento_recebido"
    ligacao = "ligacao"
    mensagem = "mensagem"
    pagamento = "pagamento"
    mudanca_responsavel = "mudanca_responsavel"
    aprovacao = "aprovacao"
    rejeicao = "rejeicao"


class CaseMovimento(Base):
    """
    Timeline unificada do caso: registro central de todos os acontecimentos.
    
    RECOMENDAÇÃO 4: Linha do tempo verdadeiramente única
    Reúne atendimento, ligação, mensagem, documento recebido, movimentação processual,
    prazo, tarefa, audiência, decisão, peça produzida, pagamento, mudança de responsável,
    análise da IA, aprovação ou rejeição humana.
    """
    __tablename__ = "case_movimentos"

    id      = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    tipo    = Column(SAEnum(CaseMovimentoTipo), nullable=False, default=CaseMovimentoTipo.nota)
    descricao = Column(Text, nullable=False)
    data_evento = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_by  = Column(String(36), nullable=True, index=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    resumo_ia   = Column(Text, nullable=True)   # andamento traduzido p/ linguagem simples (IA, rascunho)
    
    # =========================================================================
    # RECOMENDAÇÃO 4: Registro completo do evento para auditoria
    # =========================================================================
    autor_nome = Column(String(255), nullable=True)  # Nome do autor (snapshot)
    origem = Column(String(50), nullable=True)       # Origem: manual, datajud, integracao, ia, etc.
    caso_relacionado_id = Column(String(36), ForeignKey("cases.id"), nullable=True)  # Para eventos que ligam dois casos
    informacao_anterior = Column(Text, nullable=True)  # Valor anterior (para mudanças de estado)
    informacao_posterior = Column(Text, nullable=True)  # Valor posterior (para mudanças de estado)
    # =========================================================================
    
    # Relacionamentos com entidades que podem ter originado este movimento
    deadline_id = Column(String(36), ForeignKey("deadlines.id"), nullable=True, index=True)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    atendimento_id = Column(String(36), ForeignKey("atendimentos.id"), nullable=True, index=True)

    case = relationship("Case", back_populates="movimentos", foreign_keys=[case_id])
    caso_relacionado = relationship("Case", foreign_keys=[caso_relacionado_id])
    deadline = relationship("Deadline", foreign_keys=[deadline_id])
    document = relationship("Document", foreign_keys=[document_id])
    task = relationship("Task", foreign_keys=[task_id])
    atendimento = relationship("Atendimento", foreign_keys=[atendimento_id])


# Registro dos models ORM dos satélites (tabelas já existiam, sem model até P1).
# Importados aqui para garantir que o mapper conheça CaseParte/CasoArea sempre
# que case.py for carregado (as relationships acima referenciam por string).
from app.models.case_parte import CaseParte  # noqa: E402,F401
from app.models.caso_area import CasoArea    # noqa: E402,F401
