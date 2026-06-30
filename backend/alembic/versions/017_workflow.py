"""BPM Workflow — templates, etapas e histórico de execução

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE workflowstatus AS ENUM ('ativo','pausado','concluido','cancelado');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END 
        $$
    """)

    op.create_table(
        "workflow_templates",
        sa.Column("id",            sa.String(36), primary_key=True),
        sa.Column("nome",          sa.String(200), nullable=False),
        sa.Column("descricao",     sa.Text),
        sa.Column("area_juridica", sa.String(60)),
        sa.Column("is_default",    sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by",    sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",    sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",    sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at",    sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "workflow_etapas",
        sa.Column("id",              sa.String(36), primary_key=True),
        sa.Column("template_id",     sa.String(36),
                  sa.ForeignKey("workflow_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome",            sa.String(100), nullable=False),
        sa.Column("descricao",       sa.Text),
        sa.Column("ordem",           sa.Integer, nullable=False, server_default="0"),
        sa.Column("sla_dias_uteis",  sa.Integer),
        sa.Column("cor",             sa.String(20)),
        sa.Column("obrigatoria",     sa.Boolean, nullable=False, server_default="true"),
        sa.Column("acao_automatica", sa.String(50)),
    )
    op.create_index("ix_workflow_etapas_template", "workflow_etapas", ["template_id"])

    op.create_table(
        "case_workflows",
        sa.Column("id",             sa.String(36), primary_key=True),
        sa.Column("case_id",        sa.String(36),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id",    sa.String(36),
                  sa.ForeignKey("workflow_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("etapa_atual_id", sa.String(36),
                  sa.ForeignKey("workflow_etapas.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status",         PG_ENUM("ativo","pausado","concluido","cancelado",
                                            name="workflowstatus", create_type=False),
                  nullable=False, server_default="ativo"),
        sa.Column("iniciado_em",    sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("concluido_em",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by",     sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_case_workflows_case", "case_workflows", ["case_id"])

    op.create_table(
        "workflow_historico",
        sa.Column("id",               sa.String(36), primary_key=True),
        sa.Column("case_workflow_id", sa.String(36),
                  sa.ForeignKey("case_workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("etapa_id",         sa.String(36),
                  sa.ForeignKey("workflow_etapas.id", ondelete="SET NULL"), nullable=True),
        sa.Column("iniciado_em",      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("concluido_em",     sa.DateTime(timezone=True), nullable=True),
        sa.Column("responsavel_id",   sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("observacao",       sa.Text),
        sa.Column("sla_respeitado",   sa.Boolean),
    )
    op.create_index("ix_workflow_hist_cwid", "workflow_historico", ["case_workflow_id"])


def downgrade() -> None:
    op.drop_table("workflow_historico")
    op.drop_table("case_workflows")
    op.drop_table("workflow_etapas")
    op.drop_table("workflow_templates")
    op.execute("DROP TYPE IF EXISTS workflowstatus")
