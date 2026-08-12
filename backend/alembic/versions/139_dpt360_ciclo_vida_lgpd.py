"""Add DPT360 lifecycle state fields to DocumentIntakeBatch (Issue #1086).

Extends DocumentIntakeBatch with LGPD policy: states, timestamps, and
anonimization tracking for DPT360 opportunity lifecycle.

Revision ID: 139_dpt360_ciclo_vida_lgpd
Revises: 138_consolida_fontes_ingestao
Create Date: 2026-08-12 00:00:00.000000+00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "139_dpt360_ciclo_vida_lgpd"
down_revision = "138_consolida_fontes_ingestao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_intake_batches",
        sa.Column(
            "ciclo_vida_estado",
            sa.String(32),
            nullable=False,
            server_default="triagem_pendente",
        ),
    )
    op.create_index(
        "ix_document_intake_batches_ciclo_vida_estado",
        "document_intake_batches",
        ["ciclo_vida_estado"],
    )

    op.add_column(
        "document_intake_batches",
        sa.Column(
            "ciclo_vida_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.add_column(
        "document_intake_batches",
        sa.Column(
            "anonimizada_em",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_document_intake_batches_anonimizada_em",
        "document_intake_batches",
        ["anonimizada_em"],
    )

    op.add_column(
        "document_intake_batches",
        sa.Column(
            "triagem_concluida_por",
            sa.String(36),
            nullable=True,
        ),
    )

    op.add_column(
        "document_intake_batches",
        sa.Column(
            "triagem_concluida_em",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_intake_batches_anonimizada_em",
        table_name="document_intake_batches",
    )
    op.drop_column("document_intake_batches", "triagem_concluida_em")
    op.drop_column("document_intake_batches", "triagem_concluida_por")
    op.drop_column("document_intake_batches", "anonimizada_em")
    op.drop_index(
        "ix_document_intake_batches_ciclo_vida_estado",
        table_name="document_intake_batches",
    )
    op.drop_column("document_intake_batches", "ciclo_vida_updated_at")
    op.drop_column("document_intake_batches", "ciclo_vida_estado")
