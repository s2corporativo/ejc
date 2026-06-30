"""EJC v3.1 — Portal, 2FA, Templates, Embeddings 384d

Revision ID: 002_funcionalidades
Revises: 001_inicial
Create Date: 2026-06-12

Adições (sem tocar em estruturas existentes):
- users.client_id (Portal do Cliente: vincula login externo ao cliente)
- users.totp_secret + totp_enabled (2FA)
- doc_templates (templates de peças com variáveis)
- knowledge_chunks.embedding: 768 → 384 dims (all-MiniLM-L6-v2 local)
"""
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy

revision = "002_funcionalidades"
down_revision = "001_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Portal do Cliente: vínculo user ↔ client ─────────────────────
    op.add_column("users", sa.Column(
        "client_id", sa.String(36),
        sa.ForeignKey("clients.id"), nullable=True, index=True,
    ))

    # ── 2FA TOTP ─────────────────────────────────────────────────────
    op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))
    op.add_column("users", sa.Column(
        "totp_enabled", sa.Boolean, server_default="false", nullable=False,
    ))

    # ── Templates de peças ───────────────────────────────────────────
    op.create_table(
        "doc_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("tipo_peca", sa.String(50), nullable=False),
        sa.Column("area", sa.String(30)),
        sa.Column("descricao", sa.Text),
        sa.Column("conteudo", sa.Text, nullable=False),  # com {{variaveis}}
        sa.Column("ativo", sa.Boolean, server_default="true"),
        sa.Column("created_by", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── Embeddings 384d (all-MiniLM-L6-v2) ───────────────────────────
    # Coluna estava vazia (fase 2) — alteração segura sem perda de dados
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding")
    op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(384)")
    op.execute("""
        CREATE INDEX ix_knowledge_chunks_embedding
        ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding")
    op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(768)")
    op.execute("""
        CREATE INDEX ix_knowledge_chunks_embedding
        ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
    """)
    op.drop_table("doc_templates")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
    op.drop_column("users", "client_id")
