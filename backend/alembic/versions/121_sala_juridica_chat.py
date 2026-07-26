"""Sala Jurídica Conversacional — chat jurídico persistido (V1).

Cria legal_chat_sessions, legal_chat_messages, legal_chat_attachments e
legal_chat_state_versions. Estado jurídico consolidado vive como JSONB
versionado (snapshot imutável por versão).

Revision ID: 121_sala_juridica_chat
Revises: 120_chunk_pagina
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "121_sala_juridica_chat"
down_revision = "120_chunk_pagina"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_chat_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="em_analise"),
        sa.Column("favorita", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cliente_potencial", sa.String(255), nullable=True),
        sa.Column("area_sugerida", sa.String(100), nullable=True),
        sa.Column("advogado_responsavel_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("workspace_texto", sa.Text(), nullable=True),
        sa.Column("workspace_versao", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("convertido_case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("custo_ia_total", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_legal_chat_sessions_status", "legal_chat_sessions", ["status"])
    op.create_index("ix_legal_chat_sessions_status_criado", "legal_chat_sessions", ["status", "created_at"])
    op.create_index("ix_legal_chat_sessions_criador_status", "legal_chat_sessions", ["created_by", "status"])
    op.create_index("ix_legal_chat_sessions_responsavel", "legal_chat_sessions", ["advogado_responsavel_id"])
    op.create_index("ix_legal_chat_sessions_client", "legal_chat_sessions", ["client_id"])
    op.create_index("ix_legal_chat_sessions_case", "legal_chat_sessions", ["convertido_case_id"])
    op.create_index("ix_legal_chat_sessions_created_by", "legal_chat_sessions", ["created_by"])

    op.create_table(
        "legal_chat_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36),
                  sa.ForeignKey("legal_chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("autor", sa.String(10), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("modo", sa.String(40), nullable=False, server_default="conversa_livre"),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("modelo", sa.String(120), nullable=True),
        sa.Column("agente", sa.String(120), nullable=True),
        sa.Column("skills", JSONB(), nullable=False, server_default="[]"),
        sa.Column("fontes", JSONB(), nullable=False, server_default="[]"),
        sa.Column("citacoes", JSONB(), nullable=False, server_default="[]"),
        sa.Column("alertas", JSONB(), nullable=False, server_default="[]"),
        sa.Column("tokens_input", sa.Integer(), nullable=True),
        sa.Column("tokens_output", sa.Integer(), nullable=True),
        sa.Column("custo_estimado", sa.Numeric(12, 6), nullable=True),
        sa.Column("ai_log_id", sa.String(36), sa.ForeignKey("ai_logs.id"), nullable=True),
        sa.Column("estado_versao", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_legal_chat_messages_sessao", "legal_chat_messages", ["session_id", "created_at"])
    op.create_index("ix_legal_chat_messages_ai_log", "legal_chat_messages", ["ai_log_id"])

    op.create_table(
        "legal_chat_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36),
                  sa.ForeignKey("legal_chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome_original", sa.String(255), nullable=False),
        sa.Column("filepath", sa.String(500), nullable=False),
        sa.Column("mimetype", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("tipo_documento", sa.String(100), nullable=True),
        sa.Column("ocr_utilizado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resultado_analise", JSONB(), nullable=False, server_default="{}"),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", "sha256", name="uq_legal_chat_anexo_hash"),
    )
    op.create_index("ix_legal_chat_attachments_sessao", "legal_chat_attachments", ["session_id", "created_at"])

    op.create_table(
        "legal_chat_state_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36),
                  sa.ForeignKey("legal_chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("resumo", sa.Text(), nullable=True),
        sa.Column("estado", JSONB(), nullable=False, server_default="{}"),
        sa.Column("origem", sa.String(20), nullable=False, server_default="advogado"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", "versao", name="uq_legal_chat_estado_versao"),
    )
    op.create_index("ix_legal_chat_state_sessao", "legal_chat_state_versions", ["session_id", "versao"])


def downgrade() -> None:
    op.drop_table("legal_chat_state_versions")
    op.drop_table("legal_chat_attachments")
    op.drop_table("legal_chat_messages")
    op.drop_table("legal_chat_sessions")
