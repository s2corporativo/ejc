"""140_preliminares_fundacao_schema — fundação aditiva da fusão Sala + Raio-X.

Cria o schema unificado para análises preliminares sem alterar, copiar ou
remover as tabelas legadas. Nesta fase, `raio_x_*` e `legal_chat_*` continuam
sendo a fonte de verdade em runtime. Backfill, dual-write e cutover pertencem
a fases posteriores e exigem branches próprias.

Revision ID: 140_preliminares_fundacao_schema
Revises: 138_consolida_fontes_ingestao
Consolidado: 139_dpt360_ciclo_vida_lgpd
"""

revision = "140_preliminares_fundacao_schema"
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Consolidado em 2026-08-12: a bifurcação 138 → {139, 140} foi linearizada
# porque as frentes são independentes no schema — 139 altera apenas
# document_intake_batches (ciclo de vida LGPD) e 140 cria/dropa apenas as
# tabelas preliminares. A ordem 138 → 139 → 140 é segura e restaura o
# head único exigido pelos gates de governança de migrations.
down_revision = "139_dpt360_ciclo_vida_lgpd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preliminares",
        # Comuns às duas origens.
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("origem", sa.String(20), nullable=False),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("potencial_cliente", sa.String(255)),
        sa.Column("area", sa.String(100)),
        sa.Column(
            "convertido_case_id",
            sa.String(36),
            sa.ForeignKey("cases.id"),
        ),
        sa.Column("converted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("retention_until", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("discarded_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Origem = raio_x.
        sa.Column("numero_processo", sa.String(30)),
        sa.Column("subarea", sa.String(100)),
        sa.Column("rito", sa.String(100)),
        sa.Column("fase", sa.String(100)),
        sa.Column("tribunal", sa.String(50)),
        sa.Column("orgao", sa.String(100)),
        sa.Column("unidade", sa.String(100)),
        sa.Column("posicao_cliente", sa.String(100)),
        sa.Column("risco_nivel", sa.String(30)),
        sa.Column("prazo_urgente", sa.Boolean(), server_default=sa.false()),
        sa.Column(
            "origem_contextual_case_id",
            sa.String(36),
            sa.ForeignKey("cases.id"),
        ),
        sa.Column(
            "dados_extraidos",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "relatorio",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "revisao_humana",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "alertas_conflito",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "custo_ia",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
        ),
        # Origem = sala_juridica.
        sa.Column("favorita", sa.Boolean(), server_default=sa.false()),
        sa.Column(
            "client_id",
            sa.String(36),
            sa.ForeignKey("clients.id"),
        ),
        sa.Column(
            "advogado_responsavel_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
        ),
        sa.Column("workspace_texto", sa.Text()),
        sa.Column("workspace_versao", sa.Integer(), server_default="0"),
        sa.Column("frozen_at", sa.DateTime(timezone=True)),
        sa.Column("custo_ia_total", sa.Numeric(12, 6), server_default="0"),
        sa.CheckConstraint(
            "origem IN ('raio_x', 'sala_juridica')",
            name="ck_preliminares_origem",
        ),
    )
    op.create_index("ix_preliminares_origem", "preliminares", ["origem"])
    op.create_index("ix_preliminares_status", "preliminares", ["status"])
    op.create_index(
        "ix_preliminares_created_by", "preliminares", ["created_by"]
    )
    op.create_index(
        "ix_preliminares_convertido_case_id",
        "preliminares",
        ["convertido_case_id"],
    )
    op.create_index(
        "ix_preliminares_origem_contextual_case_id",
        "preliminares",
        ["origem_contextual_case_id"],
    )
    op.create_index(
        "ix_preliminares_client_id", "preliminares", ["client_id"]
    )
    op.create_index(
        "ix_preliminares_advogado_responsavel_id",
        "preliminares",
        ["advogado_responsavel_id"],
    )
    op.create_index(
        "ix_preliminares_status_criado",
        "preliminares",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_preliminares_criador_status",
        "preliminares",
        ["created_by", "status"],
    )
    op.create_index(
        "ix_preliminares_numero_processo",
        "preliminares",
        ["numero_processo"],
    )
    op.create_index("ix_preliminares_area", "preliminares", ["area"])

    op.create_table(
        "preliminar_documentos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "preliminar_id",
            sa.String(36),
            sa.ForeignKey("preliminares.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nome_original", sa.String(255), nullable=False),
        sa.Column("filepath", sa.String(500), nullable=False),
        sa.Column("mimetype", sa.String(100)),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("tipo_documento", sa.String(100)),
        sa.Column("paginas", sa.Integer()),
        sa.Column(
            "ocr_utilizado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "resultado_analise",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "uploaded_by",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "preliminar_id",
            "sha256",
            name="uq_preliminar_documento_hash",
        ),
    )
    op.create_index(
        "ix_preliminar_documentos_preliminar",
        "preliminar_documentos",
        ["preliminar_id", "created_at"],
    )

    op.create_table(
        "preliminar_mensagens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "preliminar_id",
            sa.String(36),
            sa.ForeignKey("preliminares.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("autor", sa.String(10), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column(
            "modo",
            sa.String(40),
            nullable=False,
            server_default="conversa_livre",
        ),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("modelo", sa.String(120)),
        sa.Column("agente", sa.String(120)),
        sa.Column(
            "skills",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "fontes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "citacoes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "alertas",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("tokens_input", sa.Integer()),
        sa.Column("tokens_output", sa.Integer()),
        sa.Column("custo_estimado", sa.Numeric(12, 6)),
        sa.Column("ai_log_id", sa.String(36), sa.ForeignKey("ai_logs.id")),
        sa.Column("estado_versao", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_preliminar_mensagens_preliminar",
        "preliminar_mensagens",
        ["preliminar_id", "created_at"],
    )
    op.create_index(
        "ix_preliminar_mensagens_ai_log",
        "preliminar_mensagens",
        ["ai_log_id"],
    )

    op.create_table(
        "preliminar_estados",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "preliminar_id",
            sa.String(36),
            sa.ForeignKey("preliminares.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("resumo", sa.Text()),
        sa.Column(
            "estado",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "autoria",
            sa.String(20),
            nullable=False,
            server_default="advogado",
        ),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "preliminar_id",
            "versao",
            name="uq_preliminar_estado_versao",
        ),
    )
    op.create_index(
        "ix_preliminar_estados_preliminar",
        "preliminar_estados",
        ["preliminar_id", "versao"],
    )


def downgrade() -> None:
    op.drop_table("preliminar_estados")
    op.drop_table("preliminar_mensagens")
    op.drop_table("preliminar_documentos")
    op.drop_table("preliminares")
