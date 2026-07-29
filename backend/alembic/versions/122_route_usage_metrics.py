"""Telemetria de uso das rotas candidatas à remoção (Onda 5).

Cria route_usage_metrics: uso AGREGADO por (rota, método, papel, hora), escrito
por flush periódico do contador em memória (sem INSERT por request). Sem PII —
apenas template da rota, método, papel RBAC e bucket horário.

Migration puramente ADITIVA: cria uma tabela nova; não altera nem remove nada.

Revision ID: 122_route_usage_metrics
Revises: 121_sala_juridica_chat
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "122_route_usage_metrics"
down_revision = "121_sala_juridica_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "route_usage_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rota", sa.String(length=200), nullable=False),
        sa.Column("metodo", sa.String(length=10), nullable=False),
        sa.Column("papel", sa.String(length=40), nullable=False),
        sa.Column("hora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contagem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rota", "metodo", "papel", "hora", name="uq_route_usage_bucket"),
    )
    op.create_index("ix_route_usage_metrics_rota", "route_usage_metrics", ["rota"])
    op.create_index("ix_route_usage_metrics_hora", "route_usage_metrics", ["hora"])


def downgrade() -> None:
    op.drop_index("ix_route_usage_metrics_hora", table_name="route_usage_metrics")
    op.drop_index("ix_route_usage_metrics_rota", table_name="route_usage_metrics")
    op.drop_table("route_usage_metrics")
