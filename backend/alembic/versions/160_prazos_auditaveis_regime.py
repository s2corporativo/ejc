"""Prazos processuais auditáveis: marcos, regime e revisão humana.

Revision ID: 160_prazos_auditaveis_regime
Revises: 155_indices_listagem_espinha
Create Date: 2026-09-01

Finalidade (#968)
-----------------
Separar, sem inferência retroativa, os marcos jurídicos que antes ficavam
colapsados em `data_intimacao`/`data_prazo` e registrar parâmetros suficientes
para reproduzir a decisão humana/cálculo:

- disponibilização (já existente no DJEN);
- publicação;
- termo inicial;
- vencimento (`data_prazo`, já existente);
- regime de cálculo;
- snapshot JSONB de parâmetros/resultado;
- ator e timestamp da revisão/conferência.

Risco de dados
--------------
Somente colunas nullable. NÃO há backfill: preencher publicação ou termo
inicial do legado por aproximação seria fabricar fato jurídico. Registros
antigos permanecem nulos e exigem conferência humana.

Rollback
--------
Downgrade remove apenas as colunas novas. Antes de downgrade em ambiente que
já tenha usado a funcionalidade, exportar os metadados novos porque a remoção
física perde a trilha capturada. O rollback funcional preferencial é revert do
código mantendo as colunas aditivas.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "160_prazos_auditaveis_regime"
down_revision = "159_user_cpf_secure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deadlines", sa.Column("data_publicacao", sa.Date(), nullable=True))
    op.add_column("deadlines", sa.Column("termo_inicial", sa.Date(), nullable=True))
    op.add_column(
        "deadlines", sa.Column("regime_calculo", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "deadlines",
        sa.Column("calculo_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "deadlines", sa.Column("calculado_por", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "deadlines", sa.Column("conferido_por", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "deadlines", sa.Column("conferido_em", sa.DateTime(timezone=True), nullable=True)
    )

    op.add_column(
        "djen_comunicacoes", sa.Column("data_publicacao", sa.Date(), nullable=True)
    )
    op.add_column(
        "djen_comunicacoes", sa.Column("termo_inicial", sa.Date(), nullable=True)
    )
    op.add_column(
        "djen_comunicacoes",
        sa.Column("regime_calculo", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "djen_comunicacoes",
        sa.Column("calculo_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "djen_comunicacoes",
        sa.Column("prazo_revisado_por", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "djen_comunicacoes",
        sa.Column("prazo_revisado_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("djen_comunicacoes", "prazo_revisado_em")
    op.drop_column("djen_comunicacoes", "prazo_revisado_por")
    op.drop_column("djen_comunicacoes", "calculo_metadata")
    op.drop_column("djen_comunicacoes", "regime_calculo")
    op.drop_column("djen_comunicacoes", "termo_inicial")
    op.drop_column("djen_comunicacoes", "data_publicacao")

    op.drop_column("deadlines", "conferido_em")
    op.drop_column("deadlines", "conferido_por")
    op.drop_column("deadlines", "calculado_por")
    op.drop_column("deadlines", "calculo_metadata")
    op.drop_column("deadlines", "regime_calculo")
    op.drop_column("deadlines", "termo_inicial")
    op.drop_column("deadlines", "data_publicacao")
