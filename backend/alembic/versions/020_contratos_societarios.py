"""Contratos Societários — ciclo de vida completo

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for enum_name, values in [
        ("statuscontrato", ["rascunho","em_revisao","aprovado","assinado","vigente","suspenso","expirado","rescindido"]),
        ("tipocontrato",   ["prestacao_servicos","honorarios","parceria","fornecimento","nda","societario","locacao","outros"]),
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
        "contratos_societarios",
        sa.Column("id",                        sa.String(36), primary_key=True),
        sa.Column("titulo",                    sa.String(300), nullable=False),
        sa.Column("tipo",                      PG_ENUM("prestacao_servicos","honorarios","parceria",
                                                       "fornecimento","nda","societario","locacao","outros",
                                                       name="tipocontrato", create_type=False), nullable=False),
        sa.Column("status",                    PG_ENUM("rascunho","em_revisao","aprovado","assinado",
                                                       "vigente","suspenso","expirado","rescindido",
                                                       name="statuscontrato", create_type=False),
                  nullable=False, server_default="rascunho"),
        sa.Column("partes",                    sa.Text),
        sa.Column("objeto",                    sa.Text, nullable=False),
        sa.Column("clausulas_especiais",       sa.Text),
        sa.Column("valor_total",               sa.Numeric(15, 2)),
        sa.Column("moeda",                     sa.String(3), server_default="BRL"),
        sa.Column("periodicidade",             sa.String(30)),
        sa.Column("data_assinatura",           sa.Date),
        sa.Column("data_inicio",               sa.Date),
        sa.Column("data_fim",                  sa.Date),
        sa.Column("renovacao_automatica",      sa.Boolean, nullable=False, server_default="false"),
        sa.Column("prazo_aviso_rescisao_dias", sa.Integer, server_default="30"),
        sa.Column("alertar_dias_antes",        sa.Integer, server_default="60"),
        sa.Column("documento_id",              sa.String(36),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("case_id",                   sa.String(36),
                  sa.ForeignKey("cases.id",   ondelete="SET NULL"), nullable=True),
        sa.Column("client_id",                 sa.String(36),
                  sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("observacoes",               sa.Text),
        sa.Column("tags",                      sa.Text),
        sa.Column("created_by",                sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",                sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",                sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at",                sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_contratos_status",   "contratos_societarios", ["status"])
    op.create_index("ix_contratos_data_fim", "contratos_societarios", ["data_fim"])

    op.create_table(
        "contrato_historico",
        sa.Column("id",           sa.String(36), primary_key=True),
        sa.Column("contrato_id",  sa.String(36),
                  sa.ForeignKey("contratos_societarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status_de",    sa.String(30)),
        sa.Column("status_para",  sa.String(30)),
        sa.Column("observacao",   sa.Text),
        sa.Column("alterado_por", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("alterado_em",  sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cont_hist_contrato", "contrato_historico", ["contrato_id"])


def downgrade() -> None:
    op.drop_table("contrato_historico")
    op.drop_table("contratos_societarios")
    op.execute("DROP TYPE IF EXISTS statuscontrato")
    op.execute("DROP TYPE IF EXISTS tipocontrato")
