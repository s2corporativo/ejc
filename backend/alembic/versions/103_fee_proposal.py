"""103_fee_proposal — FASE 4 do Orquestrador Jurídico.

Proposta de Honorários versionada e imutável após aprovação (fee_proposals):
  • faixas JSONB {minimo_etico, recomendado, estrategico} — mínimo ético
    VERBATIM da TabelaOABHonorario vigente; recomendado/estratégico por
    multiplicadores FIXOS do service (nunca LLM, nunca inventado);
  • origem_tabela JSONB — item OAB verbatim + fonte + vigência (ou NULL);
  • status rascunho|aprovada|rejeitada|substituida — proposta APROVADA é
    IMUTÁVEL: mudança = nova versão (anterior aprovada vira "substituida");
  • índice ÚNICO (case_id, versao) — versionamento estrito por caso.

Revision ID: 103_fee_proposal
Revises: 102_matriz_teses
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "103_fee_proposal"
down_revision = "102_matriz_teses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fee_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(15), nullable=False, server_default="rascunho"),
        sa.Column("origem_tabela", postgresql.JSONB(), nullable=True),
        sa.Column("faixas", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("exito_percentual", sa.Numeric(5, 2), nullable=True),
        sa.Column("parcelamento", postgresql.JSONB(), nullable=True),
        sa.Column("despesas_criterio", sa.Text(), nullable=True),
        sa.Column("justificativa", sa.Text(), nullable=True),
        sa.Column("criado_por", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("aprovado_por", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("aprovado_em", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_fee_proposals_case_id", "fee_proposals", ["case_id"])
    op.create_index("uq_fee_proposals_case_versao", "fee_proposals",
                    ["case_id", "versao"], unique=True)


def downgrade() -> None:
    op.drop_table("fee_proposals")
