"""Aprendizado jurídico supervisionado da IA.

Revision ID: 169_ai_supervised_learning
Revises: 168_finance_ged_links
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "169_ai_supervised_learning"
down_revision = "168_finance_ged_links"
branch_labels = None
depends_on = None

# Enum NÃO nativo (VARCHAR + CHECK): nasce e morre junto com a tabela, sem
# tipo Postgres órfão no downgrade e sem SQL bruto (gate de deploy).
EVENT_TYPE = sa.Enum(
    "correction", "error", "outcome", "benchmark",
    name="ailearningeventtype",
    native_enum=False,
    create_constraint=True,
    length=20,
)


def upgrade() -> None:
    op.create_table(
        "ai_learning_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "ai_log_id", sa.String(length=36),
            sa.ForeignKey("ai_logs.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "case_id", sa.String(length=36),
            sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "created_by", sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("event_type", EVENT_TYPE, nullable=False),
        sa.Column("area", sa.String(length=80), nullable=True),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("error_type", sa.String(length=80), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("corrected_text", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "source_refs", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "metadata_json", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "benchmark_eligible", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "approved_by", sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "difficulty IS NULL OR difficulty IN "
            "('normal','complexo','fronteira','excepcional')",
            name="ck_ai_learning_difficulty",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('baixa','media','alta','critica')",
            name="ck_ai_learning_severity",
        ),
    )
    op.create_index("ix_ai_learning_events_ai_log_id", "ai_learning_events", ["ai_log_id"])
    op.create_index("ix_ai_learning_events_case_id", "ai_learning_events", ["case_id"])
    op.create_index("ix_ai_learning_events_created_by", "ai_learning_events", ["created_by"])
    op.create_index("ix_ai_learning_events_event_type", "ai_learning_events", ["event_type"])
    op.create_index("ix_ai_learning_events_area", "ai_learning_events", ["area"])
    op.create_index("ix_ai_learning_events_difficulty", "ai_learning_events", ["difficulty"])
    op.create_index("ix_ai_learning_events_error_type", "ai_learning_events", ["error_type"])
    op.create_index("ix_ai_learning_events_severity", "ai_learning_events", ["severity"])
    op.create_index("ix_ai_learning_events_approved", "ai_learning_events", ["approved"])
    op.create_index(
        "ix_ai_learning_events_benchmark_eligible",
        "ai_learning_events", ["benchmark_eligible"],
    )
    op.create_index("ix_ai_learning_events_created_at", "ai_learning_events", ["created_at"])
    op.create_index(
        "ix_ai_learning_events_type_area_created",
        "ai_learning_events", ["event_type", "area", "created_at"],
    )
    op.create_index(
        "ix_ai_learning_events_approved_created",
        "ai_learning_events", ["approved", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("ai_learning_events")
