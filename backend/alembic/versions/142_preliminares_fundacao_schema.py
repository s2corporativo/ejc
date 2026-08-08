"""142_preliminares_fundacao_schema — F5 Fase 1: fundação de schema da fusão Raio-X + Sala Jurídica.

Cria `preliminares`, `preliminar_documentos`, `preliminar_mensagens` e
`preliminar_estados` — schema unificado para o conceito de "análise
preliminar de um caso antes de virar Caso oficial", hoje modelado
separadamente em `raio_x_analises`/`raio_x_documentos` (origem="raio_x") e
`legal_chat_sessions`/`legal_chat_messages`/`legal_chat_attachments`/
`legal_chat_state_versions` (origem="sala_juridica").

Estritamente ADITIVA (Issue #799, decisão de escopo do titular: abordagem B —
cutover aditivo — restrita a esta Fase 1 de fundação): não altera, não
renomeia e não remove nenhuma tabela existente; não migra dado; nenhum
service/router passa a usar estas tabelas ainda. `raio_x_service.py` e
`legal_chat_service.py` continuam sendo a fonte de dados em produção até as
Fases 2 (backfill + dual-write) e 3 (cutover + aposentadoria das tabelas
antigas) — nenhuma das duas faz parte desta migration.

Revision ID: 142_preliminares_fundacao_schema
Revises: 138_consolida_fontes_ingestao

Nota de numeração (ver MIGRATION_RESERVATIONS.md): no momento desta reserva
há três PRs abertos e não mesclados que também encadeiam em 138 — 139
(`139_ai_log_fk_ondelete_set_null`, PR #795), 140
(`140_legal_chat_retention_purga`, PR #803) e 141
(`141_case_despesas_processuais`, PR #806). Se qualquer um deles mesclar
primeiro, esta migration precisa ser renumerada para 143 e reencadeada na
que mesclou por último — mesmo padrão já aplicado quando o PR #786 mesclou
antes da 139 original (ver histórico da tabela de reservas).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "142_preliminares_fundacao_schema"
down_revision = "138_consolida_fontes_ingestao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preliminares",
        # ── Comuns às duas origens ────────────────────────────────────
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("origem", sa.String(20), nullable=False),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("potencial_cliente", sa.String(255)),
        sa.Column("area", sa.String(100)),
        sa.Column("convertido_case_id", sa.String(36), sa.ForeignKey("cases.id")),
        sa.Column("converted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        # Piso de purga LGPD — comum às duas origens (ver migration
        # 140_legal_chat_retention_purga, PR #803: dá o mesmo campo e a mesma
        # semântica à origem "sala_juridica" e já lê ambas em
        # services/scheduler.py::_purgar_analises_preliminares_abandonadas).
        # A Fase 2 (backfill/dual-write) deve popular esta coluna também para
        # origem="sala_juridica" — não é exclusiva de origem="raio_x".
        sa.Column("retention_until", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("discarded_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # ── Específicas de origem="raio_x" (RaioXAnalise) — nullable ────
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
        # FK para o Case que CONTEXTUALIZOU a criação deste Raio-X — não
        # confundir com o discriminador `origem` (raio_x|sala_juridica) da
        # tabela-mãe: este campo é sobre "a partir de qual caso" a análise
        # nasceu, aquele é sobre "qual produto" a gerou.
        sa.Column("origem_contextual_case_id", sa.String(36), sa.ForeignKey("cases.id")),
        sa.Column("dados_extraidos", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("relatorio", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("revisao_humana", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("alertas_conflito", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("custo_ia", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        # ── Específicas de origem="sala_juridica" (LegalChatSession) — nullable ─
        sa.Column("favorita", sa.Boolean(), server_default=sa.false()),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id")),
        sa.Column("advogado_responsavel_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("workspace_texto", sa.Text()),
        sa.Column("workspace_versao", sa.Integer(), server_default="0"),
        sa.Column("frozen_at", sa.DateTime(timezone=True)),
        sa.Column("custo_ia_total", sa.Numeric(12, 6), server_default="0"),
        sa.CheckConstraint("origem IN ('raio_x', 'sala_juridica')", name="ck_preliminares_origem"),
    )
    op.create_index("ix_preliminares_origem", "preliminares", ["origem"])
    op.create_index("ix_preliminares_status", "preliminares", ["status"])
    op.create_index("ix_preliminares_created_by", "preliminares", ["created_by"])
    op.create_index("ix_preliminares_convertido_case_id", "preliminares", ["convertido_case_id"])
    op.create_index(
        "ix_preliminares_origem_contextual_case_id", "preliminares", ["origem_contextual_case_id"]
    )
    op.create_index("ix_preliminares_client_id", "preliminares", ["client_id"])
    op.create_index(
        "ix_preliminares_advogado_responsavel_id", "preliminares", ["advogado_responsavel_id"]
    )
    op.create_index("ix_preliminares_status_criado", "preliminares", ["status", "created_at"])
    op.create_index("ix_preliminares_criador_status", "preliminares", ["created_by", "status"])
    # Preservam os índices que RaioXAnalise já tinha (raio_x.py: numero_processo
    # e area com index=True) — busca por processo (ilike) e filtro por área são
    # caminhos de consulta ativos em routers/raio_x.py hoje; criar agora, com a
    # tabela vazia, é instantâneo — na Fase 3 (tabela populada) não seria.
    op.create_index("ix_preliminares_numero_processo", "preliminares", ["numero_processo"])
    op.create_index("ix_preliminares_area", "preliminares", ["area"])

    op.create_table(
        "preliminar_documentos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "preliminar_id", sa.String(36),
            sa.ForeignKey("preliminares.id", ondelete="CASCADE"), nullable=False,
        ),
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
        sa.UniqueConstraint("preliminar_id", "sha256", name="uq_preliminar_documento_hash"),
    )
    op.create_index(
        "ix_preliminar_documentos_preliminar", "preliminar_documentos", ["preliminar_id", "created_at"]
    )

    op.create_table(
        "preliminar_mensagens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "preliminar_id", sa.String(36),
            sa.ForeignKey("preliminares.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("autor", sa.String(10), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("modo", sa.String(40), nullable=False, server_default="conversa_livre"),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("modelo", sa.String(120)),
        sa.Column("agente", sa.String(120)),
        sa.Column("skills", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fontes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("citacoes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("alertas", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tokens_input", sa.Integer()),
        sa.Column("tokens_output", sa.Integer()),
        sa.Column("custo_estimado", sa.Numeric(12, 6)),
        sa.Column("ai_log_id", sa.String(36), sa.ForeignKey("ai_logs.id")),
        sa.Column("estado_versao", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_preliminar_mensagens_preliminar", "preliminar_mensagens", ["preliminar_id", "created_at"]
    )
    op.create_index("ix_preliminar_mensagens_ai_log", "preliminar_mensagens", ["ai_log_id"])

    op.create_table(
        "preliminar_estados",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "preliminar_id", sa.String(36),
            sa.ForeignKey("preliminares.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("resumo", sa.Text()),
        sa.Column("estado", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("autoria", sa.String(20), nullable=False, server_default="advogado"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("preliminar_id", "versao", name="uq_preliminar_estado_versao"),
    )
    op.create_index(
        "ix_preliminar_estados_preliminar", "preliminar_estados", ["preliminar_id", "versao"]
    )


def downgrade() -> None:
    op.drop_table("preliminar_estados")
    op.drop_table("preliminar_mensagens")
    op.drop_table("preliminar_documentos")
    op.drop_table("preliminares")
