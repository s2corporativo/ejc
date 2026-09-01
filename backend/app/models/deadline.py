# ── app/models/deadline.py ───────────────────────────────────────────────────
from __future__ import annotations

import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class DeadlineTipo(str, enum.Enum):
    processual = "processual"  # prazo judicial
    administrativo = "administrativo"  # ex: defesa IBAMA
    interno = "interno"  # tarefa do escritório
    audiencia = "audiencia"
    prescricao = "prescricao"


class DeadlineStatus(str, enum.Enum):
    pendente = "pendente"
    concluido = "concluido"
    vencido = "vencido"
    cancelado = "cancelado"


class DeadlinePrioridade(str, enum.Enum):
    baixa = "baixa"
    media = "media"
    alta = "alta"
    critica = "critica"


def _origem_exige_confirmacao_humana(origem: str | None) -> bool:
    """Fonte única para o default seguro de prazos criados por automação.

    `djen` não entra aqui porque o único criador ativo exige aceite manual e
    vencimento informado pelo operador. `entrada_unica` também é materializada
    após confirmação explícita do rascunho. DataJud e qualquer origem `ia_*`
    nunca podem herdar o default confirmado do legado.
    """
    valor = (origem or "").strip().lower()
    return valor in {"datajud", "importacao_ia"} or valor.startswith("ia_")


class Deadline(Base):
    __tablename__ = "deadlines"

    def __init__(self, **kwargs):
        # SQLAlchemy chama este construtor somente para objetos NOVOS; carga do
        # banco não passa por aqui. Assim, a regra é aditiva e não reclassifica
        # legado em memória. O valor explícito do chamador sempre prevalece.
        if "confirmado" not in kwargs and _origem_exige_confirmacao_humana(
            kwargs.get("origem")
        ):
            kwargs["confirmado"] = False
        super().__init__(**kwargs)

    id = Column(String(36), primary_key=True)
    titulo = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    tipo = Column(
        SAEnum(DeadlineTipo),
        nullable=False,
        default=DeadlineTipo.processual,
    )
    prioridade = Column(
        SAEnum(DeadlinePrioridade),
        nullable=False,
        default=DeadlinePrioridade.media,
    )
    status = Column(
        SAEnum(DeadlineStatus),
        nullable=False,
        default=DeadlineStatus.pendente,
        index=True,
    )

    data_prazo = Column(Date, nullable=False, index=True)  # data fatal
    data_intimacao = Column(Date, nullable=True)
    data_conclusao = Column(DateTime(timezone=True), nullable=True)
    # Auditoria: id do usuário que deu baixa no prazo (par de data_conclusao).
    # String(36) sem FK, espelhando a coluna audit-actor `ciencia_confirmada_por`
    # desta mesma tabela — registra QUEM concluiu sem impor RESTRICT na exclusão
    # de usuários. Preenchimento é responsabilidade de routers/deadlines.py.
    concluido_por = Column(String(36), nullable=True)
    base_legal = Column(String(255), nullable=True)  # ex: "CPC art. 335"

    # Confirmação de ciência (audit LGPD)
    ciencia_confirmada = Column(Boolean, default=False)
    ciencia_confirmada_em = Column(DateTime(timezone=True), nullable=True)
    ciencia_confirmada_por = Column(String(36), nullable=True)

    # Alertas enviados (evita duplicação)
    alerta_7d_enviado = Column(Boolean, default=False)
    alerta_3d_enviado = Column(Boolean, default=False)
    alerta_1d_enviado = Column(Boolean, default=False)

    case_id = Column(
        String(36),
        ForeignKey("cases.id"),
        nullable=True,
        index=True,
    )
    responsavel_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    observacoes = Column(Text, nullable=True)

    # Origem e rastreabilidade. `manual` permanece o default físico para legado;
    # novas origens automatizadas são forçadas a `confirmado=False` pelo
    # construtor acima quando o chamador não fornece valor explícito.
    origem = Column(String(20), nullable=False, server_default="manual")
    referencia_datajud = Column(String(64), nullable=True, index=True)

    # Prazo automatizado/assistido nasce como RASCUNHO a confirmar. O default
    # físico TRUE preserva registros e inserts SQL legados; o ORM aplica o
    # fail-safe às origens automatizadas conhecidas.
    confirmado = Column(Boolean, nullable=False, server_default=true())
    # Rastreabilidade: documento (GED) que originou o prazo extraído por IA.
    origem_documento_id = Column(
        String(36),
        ForeignKey("documents.id"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="deadlines")
    responsavel = relationship(
        "User",
        foreign_keys=[responsavel_id],
        back_populates="deadlines",
    )
