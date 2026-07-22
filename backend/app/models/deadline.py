# ── app/models/deadline.py ───────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Date, Enum as SAEnum, func, Text, Boolean, ForeignKey, true
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class DeadlineTipo(str, enum.Enum):
    processual     = "processual"      # prazo judicial
    administrativo = "administrativo"  # ex: defesa IBAMA
    interno        = "interno"         # tarefa do escritório
    audiencia      = "audiencia"
    prescricao     = "prescricao"


class DeadlineStatus(str, enum.Enum):
    pendente  = "pendente"
    concluido = "concluido"
    vencido   = "vencido"
    cancelado = "cancelado"


class DeadlinePrioridade(str, enum.Enum):
    baixa   = "baixa"
    media   = "media"
    alta    = "alta"
    critica = "critica"


class Deadline(Base):
    __tablename__ = "deadlines"

    id        = Column(String(36), primary_key=True)
    titulo    = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    tipo      = Column(SAEnum(DeadlineTipo), nullable=False, default=DeadlineTipo.processual)
    prioridade = Column(SAEnum(DeadlinePrioridade), nullable=False, default=DeadlinePrioridade.media)
    status    = Column(SAEnum(DeadlineStatus), nullable=False, default=DeadlineStatus.pendente, index=True)

    data_prazo     = Column(Date, nullable=False, index=True)   # data fatal
    data_intimacao = Column(Date, nullable=True)
    data_conclusao = Column(DateTime(timezone=True), nullable=True)
    # Auditoria: id do usuário que deu baixa no prazo (par de data_conclusao).
    # String(36) sem FK, espelhando a coluna audit-actor `ciencia_confirmada_por`
    # desta mesma tabela — registra QUEM concluiu sem impor RESTRICT na exclusão
    # de usuários. Preenchimento é responsabilidade de routers/deadlines.py.
    concluido_por  = Column(String(36), nullable=True)
    base_legal     = Column(String(255), nullable=True)         # ex: "CPC art. 335"

    # Confirmação de ciência (audit LGPD)
    ciencia_confirmada    = Column(Boolean, default=False)
    ciencia_confirmada_em = Column(DateTime(timezone=True), nullable=True)
    ciencia_confirmada_por = Column(String(36), nullable=True)

    # Alertas enviados (evita duplicação)
    alerta_7d_enviado = Column(Boolean, default=False)
    alerta_3d_enviado = Column(Boolean, default=False)
    alerta_1d_enviado = Column(Boolean, default=False)

    case_id        = Column(String(36), ForeignKey("cases.id"), nullable=True, index=True)
    responsavel_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    observacoes    = Column(Text, nullable=True)

    # BUG-16: origem do prazo e rastreabilidade DataJud.
    # origem: 'manual' (default) | 'datajud'. referencia_datajud: chave de dedup
    # do movimento (hash CNJ+movimento) — evita reimportar o mesmo prazo.
    origem             = Column(String(20), nullable=False, server_default="manual")
    referencia_datajud = Column(String(64), nullable=True, index=True)

    # Gap C (#83): prazo extraído por IA nasce como RASCUNHO a confirmar.
    # confirmado=false marca "a confirmar" (informativo/UX + ação de confirmação);
    # NÃO filtra a lógica de alerta — o prazo já dispara alertas 7d/3d/1d normalmente.
    # Default TRUE: prazos existentes e criados manualmente são "confirmados";
    # só os extraídos por IA (origem='importacao_ia') nascem false.
    confirmado          = Column(Boolean, nullable=False, server_default=true())
    # Rastreabilidade: documento (GED) que originou o prazo extraído por IA.
    origem_documento_id = Column(
        String(36), ForeignKey("documents.id"), nullable=True, index=True
    )

    # =========================================================================
    # RECOMENDAÇÃO 5: Motor de prazos com "prova do cálculo"
    # =========================================================================
    evento_origem = Column(String(255), nullable=True)  # Evento que originou o prazo (ex: "Intimação para réplica")
    documento_origem_id = Column(String(36), ForeignKey("documents.id"), nullable=True, index=True)
    data_ciencia = Column(Date, nullable=True)  # Data da ciência oficial
    regra_legal_aplicada = Column(String(255), nullable=True)  # Ex: "CPC art. 335, 15 dias úteis"
    forma_contagem = Column(String(50), nullable=True)  # "dias_uteis" | "dias_corridos"
    calendario_utilizado = Column(String(100), nullable=True)  # Ex: "TJSP", "Justiça Federal"
    feriados_suspensoes = Column(Text, nullable=True)  # JSON ou texto descrevendo feriados/suspensões considerados
    termo_inicial = Column(Date, nullable=True)  # Data de início da contagem
    termo_final = Column(Date, nullable=True)    # Data final calculada
    calculado_por = Column(String(36), nullable=True)  # ID do usuário que calculou
    conferido_por = Column(String(36), nullable=True)  # ID do usuário que conferiu (dupla validação)
    alteracoes = Column(Text, nullable=True)  # Histórico de alterações (JSON)
    cancelamento_justificativa = Column(Text, nullable=True)  # Justificativa se cancelado
    # =========================================================================

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case        = relationship("Case", back_populates="deadlines")
    responsavel = relationship("User", foreign_keys=[responsavel_id], back_populates="deadlines")
    documento_origem = relationship("Document", foreign_keys=[documento_origem_id])
