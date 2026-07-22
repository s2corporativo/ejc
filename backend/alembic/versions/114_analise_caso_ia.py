"""114 — Módulo Análise de Caso IA (chat conversacional multi-turno).

Cria as duas tabelas do módulo:

  • analise_caso_sessoes  — cada conversa do usuário (opcionalmente atada a um
    caso via case_id ON DELETE SET NULL, para a sessão sobreviver ao caso).
  • analise_caso_mensagens — turnos user/assistant persistidos (histórico);
    ON DELETE CASCADE a partir da sessão (apagar a sessão apaga as mensagens).

Escrita À MÃO (não autogenerate): ~30 tabelas do EJC só existem em SQL bruto,
então nunca se confia no autogenerate cego para o schema completo (CLAUDE.md).

Revision ID: 114_analise_caso_ia
Revises: 112_client_pii_drop_plaintext
Create Date: 2026-07-21

Renumerada de 113 → 114 para eliminar colisão Alembic com PRs concorrentes que
também propuseram a revisão 113. Ordem canônica (issue #411): #401 ICS=113,
#405 Análise de Caso IA=114, #408=115. O down_revision permanece no head
integrado atual (112); o re-point para 113 ocorre no merge, conforme a ordem
efetiva de integração.
"""
from alembic import op
import sqlalchemy as sa


revision = "114_analise_caso_ia"
down_revision = "112_client_pii_drop_plaintext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analise_caso_sessoes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=True),
        sa.Column("titulo", sa.String(length=200), nullable=False, server_default="Nova análise"),
        sa.Column("nivel", sa.String(length=20), nullable=False, server_default="alto"),
        sa.Column("area", sa.String(length=80), nullable=True),
        sa.Column("arquivada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analise_caso_sessoes_user_id", "analise_caso_sessoes", ["user_id"])
    op.create_index("ix_analise_caso_sessoes_case_id", "analise_caso_sessoes", ["case_id"])
    op.create_index("ix_analise_caso_sessoes_arquivada", "analise_caso_sessoes", ["arquivada"])
    op.create_index("ix_analise_caso_sessoes_created_at", "analise_caso_sessoes", ["created_at"])

    op.create_table(
        "analise_caso_mensagens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sessao_id", sa.String(length=36), nullable=False),
        sa.Column("papel", sa.String(length=16), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("contexto_anexo", sa.Text(), nullable=True),
        sa.Column("anexo_nome", sa.String(length=255), nullable=True),
        sa.Column("ai_log_id", sa.String(length=36), nullable=True),
        sa.Column("is_rascunho", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["sessao_id"], ["analise_caso_sessoes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analise_caso_mensagens_sessao_id", "analise_caso_mensagens", ["sessao_id"])
    op.create_index("ix_analise_caso_mensagens_created_at", "analise_caso_mensagens", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_analise_caso_mensagens_created_at", table_name="analise_caso_mensagens")
    op.drop_index("ix_analise_caso_mensagens_sessao_id", table_name="analise_caso_mensagens")
    op.drop_table("analise_caso_mensagens")

    op.drop_index("ix_analise_caso_sessoes_created_at", table_name="analise_caso_sessoes")
    op.drop_index("ix_analise_caso_sessoes_arquivada", table_name="analise_caso_sessoes")
    op.drop_index("ix_analise_caso_sessoes_case_id", table_name="analise_caso_sessoes")
    op.drop_index("ix_analise_caso_sessoes_user_id", table_name="analise_caso_sessoes")
    op.drop_table("analise_caso_sessoes")
