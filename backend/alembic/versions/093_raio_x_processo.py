"""093_raio_x_processo — módulo preliminar autônomo Raio-X.

Revision ID: 093_raio_x_processo
Revises: 092_rag_chave_origem_vigente
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "093_raio_x_processo"
down_revision = "092_rag_chave_origem_vigente"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raio_x_analises",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("potencial_cliente", sa.String(255)),
        sa.Column("numero_processo", sa.String(30)),
        sa.Column("area", sa.String(50)),
        sa.Column("subarea", sa.String(100)),
        sa.Column("rito", sa.String(100)),
        sa.Column("fase", sa.String(100)),
        sa.Column("tribunal", sa.String(50)),
        sa.Column("orgao", sa.String(100)),
        sa.Column("unidade", sa.String(100)),
        sa.Column("posicao_cliente", sa.String(100)),
        sa.Column("status", sa.String(40), nullable=False, server_default="novo"),
        sa.Column("risco_nivel", sa.String(30)),
        sa.Column("prazo_urgente", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("origem_contextual_case_id", sa.String(36), sa.ForeignKey("cases.id")),
        sa.Column("convertido_case_id", sa.String(36), sa.ForeignKey("cases.id")),
        sa.Column("dados_extraidos", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("relatorio", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("revisao_humana", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("alertas_conflito", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("custo_ia", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True)),
        sa.Column("converted_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("discarded_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_raio_x_analises_numero_processo", "raio_x_analises", ["numero_processo"])
    op.create_index("ix_raio_x_analises_area", "raio_x_analises", ["area"])
    op.create_index("ix_raio_x_analises_status", "raio_x_analises", ["status"])
    op.create_index("ix_raio_x_analises_created_by", "raio_x_analises", ["created_by"])
    op.create_index("ix_raio_x_analises_origem_contextual_case_id", "raio_x_analises", ["origem_contextual_case_id"])
    op.create_index("ix_raio_x_analises_convertido_case_id", "raio_x_analises", ["convertido_case_id"])
    op.create_index("ix_raio_x_status_criado", "raio_x_analises", ["status", "created_at"])
    op.create_index("ix_raio_x_criador_status", "raio_x_analises", ["created_by", "status"])

    op.create_table(
        "raio_x_documentos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analise_id", sa.String(36), sa.ForeignKey("raio_x_analises.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome_original", sa.String(255), nullable=False),
        sa.Column("filepath", sa.String(500), nullable=False),
        sa.Column("mimetype", sa.String(100)),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("tipo_documento", sa.String(100)),
        sa.Column("paginas", sa.Integer()),
        sa.Column("ocr_utilizado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resultado_analise", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("analise_id", "sha256", name="uq_raio_x_documento_hash"),
    )
    op.create_index("ix_raio_x_documentos_analise", "raio_x_documentos", ["analise_id", "created_at"])


def downgrade() -> None:
    op.drop_table("raio_x_documentos")
    op.drop_table("raio_x_analises")
