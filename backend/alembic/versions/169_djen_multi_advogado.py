"""DJEN: unicidade por advogado (expansão) e evidência oficial da comunicação.

Auditoria do módulo DJEN (2026-10) — passo 1 de 2 (expand):
  • cria o índice único composto (comunicacao_id_externo, advogado_id) SEM tocar
    no índice único antigo — durante a janela entre 169 e 170 os dois coexistem
    (o composto é mais fraco que o antigo, logo nunca falha sobre dado válido);
  • persiste a evidência oficial: link do PDF, órgão e texto íntegro (sem
    tags), antes truncado em 2000 caracteres;
  • `scheduler_heartbeat.last_ok_at`: último SUCESSO real do job (base da
    janela de reconciliação do DJEN após parada/falha prolongada).

A remoção da unicidade global (que impedia a mesma comunicação de chegar a dois
advogados do escritório) está na 170.

Revision ID: 169_djen_multi_advogado
Revises: 168_finance_ged_links
Create Date: 2026-10-02
"""
import sqlalchemy as sa
from alembic import op

revision = "169_djen_multi_advogado"
down_revision = "168_finance_ged_links"
branch_labels = None
depends_on = None

# Índice UNIQUE sobre colunas que já são únicas (o composto é mais permissivo que
# o índice atual): sem risco de violação nem de lock prolongado (tabela pequena).
deployment_policy = "human_reviewed_unique_index"


def upgrade() -> None:
    op.add_column("djen_comunicacoes", sa.Column("texto_integral", sa.Text(), nullable=True))
    op.add_column("djen_comunicacoes", sa.Column("link_oficial", sa.Text(), nullable=True))
    op.add_column("djen_comunicacoes", sa.Column("orgao", sa.String(length=255), nullable=True))
    op.add_column(
        "scheduler_heartbeat",
        sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_djen_comunicacao_externo_advogado",
        "djen_comunicacoes",
        ["comunicacao_id_externo", "advogado_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_djen_comunicacao_externo_advogado", table_name="djen_comunicacoes")
    op.drop_column("scheduler_heartbeat", "last_ok_at")
    op.drop_column("djen_comunicacoes", "orgao")
    op.drop_column("djen_comunicacoes", "link_oficial")
    op.drop_column("djen_comunicacoes", "texto_integral")
