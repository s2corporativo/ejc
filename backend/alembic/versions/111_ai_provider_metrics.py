"""111 — Telemetria técnica dos provedores de IA.

Revision ID: 111_ai_provider_metrics
Revises: 110_datajud_cognitive_feed
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa


revision = "111_ai_provider_metrics"
down_revision = "110_datajud_cognitive_feed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_metrics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("task_type", sa.String(length=80), nullable=False, server_default="nao_informado"),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_brl", sa.Numeric(precision=12, scale=6), nullable=False, server_default="0"),
        sa.Column("fallback_triggered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_provider_metrics_request_id", "ai_provider_metrics", ["request_id"])
    op.create_index("ix_ai_provider_metrics_provider", "ai_provider_metrics", ["provider"])
    op.create_index("ix_ai_provider_metrics_model", "ai_provider_metrics", ["model"])
    op.create_index("ix_ai_provider_metrics_task_type", "ai_provider_metrics", ["task_type"])
    op.create_index("ix_ai_provider_metrics_status", "ai_provider_metrics", ["status"])
    op.create_index("ix_ai_provider_metrics_fallback_triggered", "ai_provider_metrics", ["fallback_triggered"])
    op.create_index("ix_ai_provider_metrics_error_type", "ai_provider_metrics", ["error_type"])
    op.create_index("ix_ai_provider_metrics_created_at", "ai_provider_metrics", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_provider_metrics_created_at", table_name="ai_provider_metrics")
    op.drop_index("ix_ai_provider_metrics_error_type", table_name="ai_provider_metrics")
    op.drop_index("ix_ai_provider_metrics_fallback_triggered", table_name="ai_provider_metrics")
    op.drop_index("ix_ai_provider_metrics_status", table_name="ai_provider_metrics")
    op.drop_index("ix_ai_provider_metrics_task_type", table_name="ai_provider_metrics")
    op.drop_index("ix_ai_provider_metrics_model", table_name="ai_provider_metrics")
    op.drop_index("ix_ai_provider_metrics_provider", table_name="ai_provider_metrics")
    op.drop_index("ix_ai_provider_metrics_request_id", table_name="ai_provider_metrics")
    op.drop_table("ai_provider_metrics")
