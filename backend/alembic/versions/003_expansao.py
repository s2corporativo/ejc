"""EJC v3.2 — Tarefas, Timesheet, Assinatura, Push, DJEN

Revision ID: 003_expansao
Revises: 002_funcionalidades
Create Date: 2026-06-12

Novas estruturas (aditivas):
- tasks: kanban interno por caso
- time_entries: timesheet faturável
- signature_requests: assinatura eletrônica no Portal (MP 2.200-2/2001)
- push_subscriptions: Web Push (alertas no celular)
- djen_comunicacoes: intimações capturadas do DJEN/Comunica (CNJ)
- users.djen_oab_numero/uf: OAB para consulta de intimações
"""
from alembic import op
import sqlalchemy as sa

revision = "003_expansao"
down_revision = "002_funcionalidades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── OAB p/ captura de intimações DJEN ─────────────────────────────
    op.add_column("users", sa.Column("djen_oab_numero", sa.String(10), nullable=True))
    op.add_column("users", sa.Column("djen_oab_uf", sa.String(2), nullable=True))

    # ── Tarefas (kanban) ──────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("descricao", sa.Text),
        sa.Column("status", sa.Enum("a_fazer", "fazendo", "concluida",
                  name="taskstatus"), nullable=False,
                  server_default="a_fazer", index=True),
        sa.Column("prioridade", sa.String(10), server_default="media"),
        sa.Column("data_limite", sa.Date),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), index=True),
        sa.Column("responsavel_id", sa.String(36), sa.ForeignKey("users.id"), index=True),
        sa.Column("criado_por", sa.String(36)),
        sa.Column("concluida_em", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── Timesheet ─────────────────────────────────────────────────────
    op.create_table(
        "time_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"),
                  nullable=False, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("data", sa.Date, nullable=False),
        sa.Column("minutos", sa.Integer, nullable=False),
        sa.Column("descricao", sa.String(500), nullable=False),
        sa.Column("faturavel", sa.Boolean, server_default="true"),
        sa.Column("fee_id", sa.String(36), sa.ForeignKey("fees.id"),
                  nullable=True, index=True),  # preenchido ao faturar
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── Assinatura eletrônica ─────────────────────────────────────────
    op.create_table(
        "signature_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"),
                  nullable=False, index=True),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"),
                  nullable=False, index=True),
        sa.Column("status", sa.Enum("pendente", "assinado", "cancelado",
                  name="signaturestatus"), nullable=False,
                  server_default="pendente", index=True),
        sa.Column("hash_sha256", sa.String(64), nullable=False),  # do arquivo
        sa.Column("assinado_em", sa.DateTime(timezone=True)),
        sa.Column("assinado_por_user", sa.String(36)),  # user do portal
        sa.Column("ip", sa.String(45)),
        sa.Column("user_agent", sa.String(300)),
        sa.Column("criado_por", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── Web Push subscriptions ────────────────────────────────────────
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("endpoint", sa.String(500), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(255), nullable=False),
        sa.Column("auth", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Intimações DJEN (dedup + tratamento) ──────────────────────────
    op.create_table(
        "djen_comunicacoes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("comunicacao_id_externo", sa.String(64), nullable=False,
                  unique=True, index=True),
        sa.Column("advogado_id", sa.String(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("numero_processo", sa.String(30), index=True),
        sa.Column("tribunal", sa.String(20)),
        sa.Column("tipo_comunicacao", sa.String(60)),
        sa.Column("data_disponibilizacao", sa.Date, index=True),
        sa.Column("texto_resumo", sa.Text),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"),
                  nullable=True, index=True),
        sa.Column("processada", sa.Boolean, server_default="false", index=True),
        sa.Column("processada_por", sa.String(36)),
        sa.Column("processada_em", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("djen_comunicacoes")
    op.drop_table("push_subscriptions")
    op.drop_table("signature_requests")
    op.drop_table("time_entries")
    op.drop_table("tasks")
    op.execute("DROP TYPE IF EXISTS signaturestatus")
    op.execute("DROP TYPE IF EXISTS taskstatus")
    op.drop_column("users", "djen_oab_uf")
    op.drop_column("users", "djen_oab_numero")
