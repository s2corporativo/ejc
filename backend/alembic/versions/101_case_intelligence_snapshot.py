"""101_case_intelligence_snapshot — FASE 1 do Orquestrador Jurídico.

Cria `case_intelligence_snapshots`: fotografia VERSIONADA da inteligência do
caso (triagem, intake, raio_x, motor_peca, manual). Append-only: cada análise
gera uma versão nova por caso (nunca sobrescreve); aprovação humana (HITL)
congela o snapshot (congelado=true + aprovado_por/aprovado_em).

Índices:
  • ix_case_intelligence_snapshots_case_id — lookups por caso;
  • uq_cis_case_versao (case_id, versao) ÚNICO — integridade do versionamento
    (blinda o max+1 contra corrida: IntegrityError, nunca versão duplicada).

Revision ID: 101_case_intelligence_snapshot
Revises: 100_vw_atividades_enriquecida
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "101_case_intelligence_snapshot"
down_revision = "100_vw_atividades_enriquecida"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_intelligence_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("origem", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("resumo", sa.Text()),
        sa.Column("ai_log_ids", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("criado_por", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("congelado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("aprovado_por", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("aprovado_em", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_case_intelligence_snapshots_case_id",
                    "case_intelligence_snapshots", ["case_id"])
    op.create_index("uq_cis_case_versao", "case_intelligence_snapshots",
                    ["case_id", "versao"], unique=True)


def downgrade() -> None:
    op.drop_table("case_intelligence_snapshots")
