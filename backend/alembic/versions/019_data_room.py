"""Data Room — salas de documentos com links de acesso controlado

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_rooms",
        sa.Column("id",         sa.String(36), primary_key=True),
        sa.Column("nome",       sa.String(200), nullable=False),
        sa.Column("descricao",  sa.Text),
        sa.Column("case_id",    sa.String(36),
                  sa.ForeignKey("cases.id",   ondelete="SET NULL"), nullable=True),
        sa.Column("client_id",  sa.String(36),
                  sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.String(36),
                  sa.ForeignKey("users.id",   ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "data_room_arquivos",
        sa.Column("id",             sa.String(36), primary_key=True),
        sa.Column("data_room_id",   sa.String(36),
                  sa.ForeignKey("data_rooms.id",  ondelete="CASCADE"), nullable=False),
        sa.Column("document_id",    sa.String(36),
                  sa.ForeignKey("documents.id",   ondelete="CASCADE"), nullable=False),
        sa.Column("nome_exibicao",  sa.String(300)),
        sa.Column("adicionado_por", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("added_at",       sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dr_arquivos_room",     "data_room_arquivos", ["data_room_id"])
    op.create_index("ix_dr_arquivos_document", "data_room_arquivos", ["document_id"])

    op.create_table(
        "data_room_links",
        sa.Column("id",                 sa.String(36), primary_key=True),
        sa.Column("data_room_id",       sa.String(36),
                  sa.ForeignKey("data_rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token",              sa.String(64), unique=True, nullable=False),
        sa.Column("descricao",          sa.String(200)),
        sa.Column("expira_em",          sa.DateTime(timezone=True)),
        sa.Column("max_acessos",        sa.Integer),
        sa.Column("acessos_realizados", sa.Integer, nullable=False, server_default="0"),
        sa.Column("senha_hash",         sa.String(128)),
        sa.Column("ativo",              sa.Boolean, nullable=False, server_default="true"),
        sa.Column("criado_por",         sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",         sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dr_links_token",   "data_room_links", ["token"])
    op.create_index("ix_dr_links_room",    "data_room_links", ["data_room_id"])

    op.create_table(
        "data_room_acesso_logs",
        sa.Column("id",          sa.String(36), primary_key=True),
        sa.Column("link_id",     sa.String(36),
                  sa.ForeignKey("data_room_links.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ip",          sa.String(45)),
        sa.Column("user_agent",  sa.Text),
        sa.Column("acessado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_dr_acesso_link", "data_room_acesso_logs", ["link_id"])


def downgrade() -> None:
    op.drop_table("data_room_acesso_logs")
    op.drop_table("data_room_links")
    op.drop_table("data_room_arquivos")
    op.drop_table("data_rooms")
