"""161 — estorno de pagamentos de honorário (subledger apend-only).

Fecha o achado P2 da homologação de 18/09/2026: os guards de
``routers/fees.py`` exigiam "registre eventual estorno em fluxo próprio",
mas o fluxo não existia — honorário pago com erro de lançamento ficava
sem caminho de correção auditável.

Tabela aditiva: cada estorno referencia o pagamento de origem e o fee,
com valor, motivo obrigatório e data. Nada é editado ou apagado do
``fee_payments`` — o estorno é um lançamento novo que ``total_pago_efetivo``
subtrai, e a reabertura do honorário ocorre no endpoint com audit log.

Revision ID: 161_fee_estornos
Revises: 160_activity_alert_states
"""
from alembic import op
import sqlalchemy as sa

revision = "161_fee_estornos"
down_revision = "160_activity_alert_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fee_estornos",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "fee_id",
            sa.String(length=36),
            sa.ForeignKey("fees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "fee_payment_id",
            sa.String(length=36),
            sa.ForeignKey("fee_payments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("data_estorno", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_fee_estornos_fee_id", "fee_estornos", ["fee_id"]
    )
    op.create_index(
        "ix_fee_estornos_fee_payment_id", "fee_estornos", ["fee_payment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_fee_estornos_fee_payment_id", table_name="fee_estornos")
    op.drop_index("ix_fee_estornos_fee_id", table_name="fee_estornos")
    op.drop_table("fee_estornos")
