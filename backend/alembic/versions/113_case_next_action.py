"""113 — Núcleo operacional: próxima ação canônica e exceções auditadas.

Cria duas estruturas aditivas:

* case_next_actions: histórico imutável de ações operacionais; um índice parcial
  garante no máximo uma ação atual (não concluída) por caso.
* case_next_action_waivers: exceções temporárias e justificadas para um caso
  permanecer sem próxima ação; também preserva histórico e autoria.

Não há backfill inventado. Casos legados permanecem sem ação e passam a ser
sinalizados pelo índice operacional de saúde. O enforcement bloqueante é
ativado separadamente por feature flag após reconciliação.

Revision ID: 113_case_next_action
Revises: 112_client_pii_drop_plaintext
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa


revision = "113_case_next_action"
down_revision = "112_client_pii_drop_plaintext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_next_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "urgency",
            sa.String(length=12),
            nullable=False,
            server_default=sa.text("'media'"),
        ),
        sa.Column(
            "blocked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column(
            "waiting_on",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'ninguem'"),
        ),
        sa.Column(
            "origin_type",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column("origin_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by", sa.String(length=36), nullable=True),
        sa.Column("completion_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "urgency IN ('baixa','media','alta','critica')",
            name="ck_case_next_actions_urgency",
        ),
        sa.CheckConstraint(
            "waiting_on IN ('ninguem','cliente','terceiro','tribunal','interno')",
            name="ck_case_next_actions_waiting_on",
        ),
        sa.CheckConstraint(
            "origin_type IN ('manual','documento','movimento','prazo','tarefa')",
            name="ck_case_next_actions_origin_type",
        ),
        sa.CheckConstraint(
            "(blocked = false) OR "
            "(blocked_reason IS NOT NULL AND length(trim(blocked_reason)) >= 5)",
            name="ck_case_next_actions_blocked_reason",
        ),
        sa.CheckConstraint(
            "(waiting_on = 'ninguem') OR blocked = true",
            name="ck_case_next_actions_waiting_requires_block",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["completed_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_case_next_actions_case_id",
        "case_next_actions",
        ["case_id"],
    )
    op.create_index(
        "ix_case_next_actions_owner_id",
        "case_next_actions",
        ["owner_id"],
    )
    op.create_index(
        "ix_case_next_actions_due_at",
        "case_next_actions",
        ["due_at"],
    )
    op.create_index(
        "uq_case_next_actions_current",
        "case_next_actions",
        ["case_id"],
        unique=True,
        postgresql_where=sa.text("completed_at IS NULL"),
    )

    op.create_table(
        "case_next_action_waivers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "length(trim(reason)) >= 10",
            name="ck_case_next_action_waivers_reason",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_case_next_action_waivers_expiry",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_case_next_action_waivers_case_id",
        "case_next_action_waivers",
        ["case_id"],
    )
    op.create_index(
        "uq_case_next_action_waivers_current",
        "case_next_action_waivers",
        ["case_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_case_next_action_waivers_current",
        table_name="case_next_action_waivers",
    )
    op.drop_index(
        "ix_case_next_action_waivers_case_id",
        table_name="case_next_action_waivers",
    )
    op.drop_table("case_next_action_waivers")

    op.drop_index(
        "uq_case_next_actions_current",
        table_name="case_next_actions",
    )
    op.drop_index(
        "ix_case_next_actions_due_at",
        table_name="case_next_actions",
    )
    op.drop_index(
        "ix_case_next_actions_owner_id",
        table_name="case_next_actions",
    )
    op.drop_index(
        "ix_case_next_actions_case_id",
        table_name="case_next_actions",
    )
    op.drop_table("case_next_actions")
