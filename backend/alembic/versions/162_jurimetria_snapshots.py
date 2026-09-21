"""Jurimetria externa: snapshots exclusivamente agregados/minimizados.

Revision ID: 162_jurimetria_snapshots
Revises: 161_fee_estornos

Finalidade
----------
Persistir séries históricas da jurimetria DataJud sem reativar o schema legado
jur_processos/jur_partes/raw_datajud. A tabela guarda apenas filtros do recorte
e o agregado estatístico já sanitizado pelo serviço.

Upgrade é expand-only. Downgrade remove somente esta tabela/índices e não toca
nas tabelas jur_* históricas nem em dados de casos.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "162_jurimetria_snapshots"
down_revision = "161_fee_estornos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jurimetria_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("snapshot_key", sa.String(64), nullable=False, unique=True),
        sa.Column("fonte", sa.String(160), nullable=False),
        sa.Column("tribunal", sa.String(20), nullable=False),
        sa.Column("filtros", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("agregado", JSONB, nullable=False),
        sa.Column("tpu_versao", sa.String(40), nullable=True),
        sa.Column("n_documentos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("amostra_truncada", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_jurimetria_snapshots_snapshot_key",
        "jurimetria_snapshots",
        ["snapshot_key"],
        unique=True,
    )
    op.create_index(
        "ix_jurimetria_snapshots_tribunal_coleta",
        "jurimetria_snapshots",
        ["tribunal", "coletado_em"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_jurimetria_snapshots_tribunal_coleta",
        table_name="jurimetria_snapshots",
    )
    op.drop_index(
        "ix_jurimetria_snapshots_snapshot_key",
        table_name="jurimetria_snapshots",
    )
    op.drop_table("jurimetria_snapshots")
