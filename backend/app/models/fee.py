# ── app/models/fee.py ────────────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import (
    Column, String, DateTime, Date, Enum as SAEnum, func, Text, Numeric,
    ForeignKey, UniqueConstraint, Boolean, Integer, CheckConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class FeeTipo(str, enum.Enum):
    fixo        = "fixo"
    exito       = "exito"           # percentual sobre resultado
    misto       = "misto"
    por_hora    = "por_hora"
    custas_despesas = "custas_despesas"  # reembolso de despesas
    # Adicionado ao FINAL para casar com a ordem do tipo nativo `feetipo` no
    # Postgres, onde `ALTER TYPE ... ADD VALUE` (migration 097) anexa ao fim.
    sucumbencia = "sucumbencia"     # honorários de sucumbência (CPC art. 85)


class FeeStatus(str, enum.Enum):
    pendente  = "pendente"
    pago      = "pago"
    atrasado  = "atrasado"
    cancelado = "cancelado"


class Fee(Base):
    __tablename__ = "fees"

    id     = Column(String(36), primary_key=True)
    tipo   = Column(SAEnum(FeeTipo), nullable=False, default=FeeTipo.fixo)
    status = Column(SAEnum(FeeStatus), nullable=False, default=FeeStatus.pendente, index=True)

    descricao         = Column(String(255), nullable=False)
    valor             = Column(Numeric(14, 2), nullable=True)
    percentual_exito  = Column(Numeric(5, 2),  nullable=True)
    data_vencimento   = Column(Date, nullable=True, index=True)
    data_pagamento    = Column(Date, nullable=True)

    case_id   = Column(String(36), ForeignKey("cases.id"),   nullable=True, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    observacoes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case     = relationship("Case",   back_populates="fees")
    client   = relationship("Client", back_populates="fees")
    payments = relationship("FeePayment", back_populates="fee")
    installments = relationship(
        "FeeInstallment",
        back_populates="fee",
        order_by="FeeInstallment.installment_number",
        cascade="save-update, merge",
    )


class FeeInstallment(Base):
    """Parcela individual de um contrato de honorários.

    Fee permanece o recebível mestre e FeePayment continua sendo a
    fonte soberana de entrada de caixa. Esta tabela representa somente o
    cronograma financeiro do contrato.
    """

    __tablename__ = "fee_installments"
    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_fee_installments_amount_positive",
        ),
        CheckConstraint(
            "installment_number >= 1",
            name="ck_fee_installments_number_positive",
        ),
        CheckConstraint(
            "installment_count >= 1",
            name="ck_fee_installments_count_positive",
        ),
        CheckConstraint(
            "installment_number <= installment_count",
            name="ck_fee_installments_number_lte_count",
        ),
        CheckConstraint(
            "kind IN ('entrada', 'parcela')",
            name="ck_fee_installments_kind",
        ),
        UniqueConstraint(
            "contract_document_id",
            "installment_number",
            name="uq_fee_installments_contract_number",
        ),
        Index(
            "ix_fee_installments_client_due",
            "client_id",
            "due_date",
        ),
        Index(
            "ix_fee_installments_status_due",
            "status",
            "due_date",
        ),
    )

    id = Column(String(36), primary_key=True)
    fee_id = Column(
        String(36),
        ForeignKey("fees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_document_id = Column(
        String(36),
        ForeignKey("legal_docs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    client_id = Column(
        String(36),
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
    )

    installment_number = Column(Integer, nullable=False)
    installment_count = Column(Integer, nullable=False)
    kind = Column(String(20), nullable=False, default="parcela")

    amount = Column(Numeric(14, 2), nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(
        SAEnum(FeeStatus, name="feestatus"),
        nullable=False,
        default=FeeStatus.pendente,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    fee = relationship("Fee", back_populates="installments")
    contract_document = relationship("LegalDoc")
    client = relationship("Client")
    payments = relationship(
        "FeePayment",
        back_populates="installment",
        cascade="save-update, merge",
    )


class FeePayment(Base):
    """Pagamentos parciais de um honorário."""
    __tablename__ = "fee_payments"

    id     = Column(String(36), primary_key=True)
    fee_id = Column(String(36), ForeignKey("fees.id"), nullable=False, index=True)
    # NULL = pagamento legado ou ainda não alocado a uma parcela específica.
    installment_id = Column(
        String(36),
        ForeignKey("fee_installments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    valor  = Column(Numeric(14, 2), nullable=False)
    data_pagamento = Column(Date, nullable=False)
    forma  = Column(String(30), nullable=True)   # pix|transferencia|dinheiro|cartao
    comprovante_doc_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    fee = relationship("Fee", back_populates="payments")
    installment = relationship(
        "FeeInstallment",
        back_populates="payments",
    )
    estornos = relationship(
        "FeeEstorno",
        back_populates="pagamento",
        cascade="save-update, merge",
    )


class FeeEstorno(Base):
    """Estorno (reversão) de um pagamento de honorário — fluxo próprio e
    auditável (fechamento do achado P2 da homologação 18/09/2026).

    O ledger é APEND-ONLY: nunca se edita nem se apaga um ``FeePayment``.
    O estorno é um lançamento novo, amarrado ao pagamento de origem, com
    motivo obrigatório. ``total_pago_efetivo`` subtrai estornos, e a
    reabertura do honorário (``pago`` → ``pendente``/``atrasado``) acontece
    no endpoint, sob auditoria — nunca por edição silenciosa de status.
    """

    __tablename__ = "fee_estornos"

    id             = Column(String(36), primary_key=True)
    fee_id         = Column(
        String(36), ForeignKey("fees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fee_payment_id = Column(
        String(36),
        ForeignKey("fee_payments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    valor        = Column(Numeric(14, 2), nullable=False)
    motivo       = Column(Text, nullable=False)
    data_estorno = Column(Date, nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    pagamento = relationship("FeePayment", back_populates="estornos")


class FeeCobrancaEnvio(Base):
    """Degrau da régua de cobrança ao CLIENTE já enviado para uma parcela
    (migration 084). UNIQUE(fee_id, degrau) = idempotência: no máximo um envio
    por degrau por parcela (services/cobranca_cliente_service.py).

    `degrau` ∈ {d-3, d+1, d+7, d+15, escalado_advogado} — validação de domínio
    na aplicação (VARCHAR, mesmo trade-off das tabelas raw-SQL do projeto).
    """
    __tablename__ = "fee_cobranca_envios"
    __table_args__ = (
        UniqueConstraint("fee_id", "degrau",
                         name="uq_fee_cobranca_envios_fee_degrau"),
    )

    id     = Column(String(36), primary_key=True)
    fee_id = Column(String(36), ForeignKey("fees.id"), nullable=False, index=True)
    degrau = Column(String(20), nullable=False)
    enviado_em = Column(DateTime(timezone=True), server_default=func.now())


class CommissionRule(Base):
    """Regra de comissão versionada por vigência e escopo."""
    __tablename__ = "commission_rules"

    id = Column(String(36), primary_key=True)
    nome = Column(String(120), nullable=False)
    escopo = Column(String(20), nullable=False)
    area = Column(String(50), nullable=True, index=True)
    advogado_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    percentual_advogado = Column(Numeric(5, 2), nullable=False)
    descontar_despesas = Column(Boolean, nullable=False, default=True)
    prioridade = Column(Integer, nullable=False, default=100)
    ativo = Column(Boolean, nullable=False, default=True)
    vigencia_inicio = Column(Date, nullable=False, server_default=func.current_date())
    vigencia_fim = Column(Date, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class CaseReceiptAllocation(Base):
    """Rateio econômico de um recebimento lançado pelo fluxo do caso.

    Não substitui FeePayment: a entrada de caixa continua no subledger
    canônico. Esta tabela registra apenas a destinação econômica do pagamento.
    """
    __tablename__ = "case_receipt_allocations"
    __table_args__ = (
        UniqueConstraint("fee_payment_id", name="uq_case_receipt_alloc_payment"),
    )

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    fee_payment_id = Column(String(36), ForeignKey("fee_payments.id", ondelete="RESTRICT"), nullable=False, index=True)
    advogado_responsavel_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    percentual_advogado = Column(Numeric(5, 2), nullable=False)
    valor_advogado = Column(Numeric(14, 2), nullable=False)
    valor_escritorio = Column(Numeric(14, 2), nullable=False)
    regra = Column(String(50), nullable=False)
    commission_rule_id = Column(String(36), ForeignKey("commission_rules.id", ondelete="SET NULL"), nullable=True, index=True)
    bruto_recebido = Column(Numeric(14, 2), nullable=False)
    despesas_deduzidas = Column(Numeric(14, 2), nullable=False, default=0)
    base_liquida = Column(Numeric(14, 2), nullable=False)
    withdrawal_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
