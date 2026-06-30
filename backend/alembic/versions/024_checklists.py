"""Checklists Jurídicos — templates e instâncias por caso

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for enum_name, values in [
        ("checklistitemcategoria", ["documentos","diligencias","prazos","audiencia","financeiro","comunicacao","outros"]),
        ("checkliststatus",        ["em_andamento","concluido","cancelado"]),
    ]:
        vals = ",".join(f"'{v}'" for v in values)
        op.execute(f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{enum_name}') THEN
                    CREATE TYPE {enum_name} AS ENUM ({vals});
                END IF;
            END $$
        """)

    op.create_table(
        "checklist_templates",
        sa.Column("id",              sa.String(36), primary_key=True),
        sa.Column("nome",            sa.String(200), nullable=False),
        sa.Column("descricao",       sa.Text),
        sa.Column("area_juridica",   sa.String(60)),
        sa.Column("fase_processual", sa.String(80)),
        sa.Column("tags",            sa.Text),
        sa.Column("is_default",      sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by",      sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at",      sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "checklist_template_items",
        sa.Column("id",          sa.String(36), primary_key=True),
        sa.Column("template_id", sa.String(36),
                  sa.ForeignKey("checklist_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("texto",       sa.String(500), nullable=False),
        sa.Column("dica",        sa.Text),
        sa.Column("categoria",   PG_ENUM("documentos","diligencias","prazos","audiencia",
                                         "financeiro","comunicacao","outros",
                                         name="checklistitemcategoria", create_type=False),
                  nullable=False, server_default="outros"),
        sa.Column("obrigatorio", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("ordem",       sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_checklist_ti_template", "checklist_template_items", ["template_id"])

    op.create_table(
        "case_checklists",
        sa.Column("id",          sa.String(36), primary_key=True),
        sa.Column("case_id",     sa.String(36),
                  sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.String(36),
                  sa.ForeignKey("checklist_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("nome",        sa.String(200), nullable=False),
        sa.Column("status",      PG_ENUM("em_andamento","concluido","cancelado",
                                         name="checkliststatus", create_type=False),
                  nullable=False, server_default="em_andamento"),
        sa.Column("total_itens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("itens_ok",    sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by",  sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",  sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_case_checklists_case", "case_checklists", ["case_id"])

    op.create_table(
        "case_checklist_items",
        sa.Column("id",                sa.String(36), primary_key=True),
        sa.Column("case_checklist_id", sa.String(36),
                  sa.ForeignKey("case_checklists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_item_id",  sa.String(36),
                  sa.ForeignKey("checklist_template_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("texto",             sa.String(500), nullable=False),
        sa.Column("dica",              sa.Text),
        sa.Column("categoria",         PG_ENUM("documentos","diligencias","prazos","audiencia",
                                               "financeiro","comunicacao","outros",
                                               name="checklistitemcategoria", create_type=False),
                  nullable=False, server_default="outros"),
        sa.Column("obrigatorio",       sa.Boolean, nullable=False, server_default="true"),
        sa.Column("ordem",             sa.Integer, nullable=False, server_default="0"),
        sa.Column("concluido",         sa.Boolean, nullable=False, server_default="false"),
        sa.Column("concluido_por",     sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("concluido_em",      sa.DateTime(timezone=True), nullable=True),
        sa.Column("observacao",        sa.Text),
    )
    op.create_index("ix_case_checklist_items_cl", "case_checklist_items", ["case_checklist_id"])


def downgrade() -> None:
    op.drop_table("case_checklist_items")
    op.drop_table("case_checklists")
    op.drop_table("checklist_template_items")
    op.drop_table("checklist_templates")
    op.execute("DROP TYPE IF EXISTS checkliststatus")
    op.execute("DROP TYPE IF EXISTS checklistitemcategoria")
