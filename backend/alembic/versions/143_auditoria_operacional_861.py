"""143 — auditoria operacional: prazos, financeiro, portal e assinaturas.

Upgrade expand-only com backfill aditivo apenas de signatários legados. Não
presume publicação externa de documentos antigos nem confirmação fiscal de
cancelamentos históricos.

Revision ID: 143_auditoria_operacional_861
Revises: 138_consolida_fontes_ingestao
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "143_auditoria_operacional_861"
down_revision = "138_consolida_fontes_ingestao"
branch_labels = None
depends_on = None

deployment_policy = "additive_data_backfill"
data_backfill_targets = ("signature_signers",)


def upgrade() -> None:
    op.add_column("deadlines", sa.Column("data_publicacao", sa.Date(), nullable=True))
    op.add_column("deadlines", sa.Column("termo_inicial", sa.Date(), nullable=True))
    op.add_column(
        "deadlines", sa.Column("regime_calculo", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "deadlines",
        sa.Column(
            "calculo_automatico",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_deadlines_regime_calculo", "deadlines", ["regime_calculo"], unique=False
    )

    op.add_column(
        "office_expenses",
        sa.Column("recorrencia_origem_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_office_expenses_recorrencia_origem",
        "office_expenses",
        "office_expenses",
        ["recorrencia_origem_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_office_expenses_recorrencia_origem",
        "office_expenses",
        ["recorrencia_origem_id"],
        unique=False,
    )

    op.add_column(
        "documents",
        sa.Column(
            "publicado_portal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "documents", sa.Column("publicado_em", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "documents", sa.Column("publicado_por", sa.String(length=36), nullable=True)
    )
    op.create_foreign_key(
        "fk_documents_publicado_por_users",
        "documents",
        "users",
        ["publicado_por"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_documents_publicado_portal", "documents", ["publicado_portal"], unique=False
    )

    op.create_table(
        "signature_signers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "signature_request_id",
            sa.String(length=36),
            sa.ForeignKey("signature_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("nome_snapshot", sa.String(length=255), nullable=True),
        sa.Column("email_snapshot", sa.String(length=320), nullable=False),
        sa.Column(
            "papel_snapshot",
            sa.String(length=80),
            nullable=False,
            server_default="cliente",
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pendente"
        ),
        sa.Column("assinado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pendente','assinado','recusado')",
            name="ck_signature_signers_status_enum",
        ),
        sa.UniqueConstraint(
            "signature_request_id",
            "user_id",
            name="uq_signature_signers_request_user",
        ),
    )
    op.create_index(
        "ix_signature_signers_request",
        "signature_signers",
        ["signature_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_signature_signers_user", "signature_signers", ["user_id"], unique=False
    )
    op.create_index(
        "ix_signature_signers_status", "signature_signers", ["status"], unique=False
    )
    op.execute(
        """
        INSERT INTO signature_signers
            (id, signature_request_id, user_id, nome_snapshot,
             email_snapshot, papel_snapshot, status, assinado_em, ip,
             user_agent, created_at)
        SELECT substr(md5('signature-signer:' || sr.id || ':' || sr.assinado_por_user),1,8)
               ||'-'||substr(md5('signature-signer:' || sr.id || ':' || sr.assinado_por_user),9,4)
               ||'-'||substr(md5('signature-signer:' || sr.id || ':' || sr.assinado_por_user),13,4)
               ||'-'||substr(md5('signature-signer:' || sr.id || ':' || sr.assinado_por_user),17,4)
               ||'-'||substr(md5('signature-signer:' || sr.id || ':' || sr.assinado_por_user),21,12),
               sr.id, sr.assinado_por_user, u.full_name, u.email,
               'cliente', 'assinado', sr.assinado_em, sr.ip, sr.user_agent,
               sr.created_at
          FROM signature_requests sr
          JOIN users u ON u.id = sr.assinado_por_user
         WHERE sr.deleted_at IS NULL
           AND sr.status::text = 'assinado'
           AND sr.assinado_por_user IS NOT NULL
        ON CONFLICT (signature_request_id, user_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO signature_signers
            (id, signature_request_id, user_id, nome_snapshot,
             email_snapshot, papel_snapshot, status, created_at)
        SELECT substr(md5('signature-signer:' || sr.id || ':' || u.id),1,8)
               ||'-'||substr(md5('signature-signer:' || sr.id || ':' || u.id),9,4)
               ||'-'||substr(md5('signature-signer:' || sr.id || ':' || u.id),13,4)
               ||'-'||substr(md5('signature-signer:' || sr.id || ':' || u.id),17,4)
               ||'-'||substr(md5('signature-signer:' || sr.id || ':' || u.id),21,12),
               sr.id, u.id, u.full_name, u.email,
               'cliente', 'pendente', sr.created_at
          FROM signature_requests sr
          JOIN users u ON u.client_id = sr.client_id
         WHERE sr.deleted_at IS NULL
           AND sr.status::text = 'pendente'
           AND u.role::text = 'cliente_externo'
           AND u.is_active = TRUE
           AND u.deleted_at IS NULL
        ON CONFLICT (signature_request_id, user_id) DO NOTHING
        """
    )

    op.add_column(
        "notas_fiscais_servico",
        sa.Column("cancelamento_tipo", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "notas_fiscais_servico",
        sa.Column(
            "cancelamento_fiscal_confirmado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "notas_fiscais_servico",
        sa.Column(
            "cancelamento_confirmado_em", sa.DateTime(timezone=True), nullable=True
        ),
    )

    op.add_column(
        "socios", sa.Column("meta_produtividade", sa.Numeric(12, 2), nullable=True)
    )
    op.create_table(
        "socios_historico",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "socio_id",
            sa.String(length=36),
            sa.ForeignKey("socios.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "alterado_por",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("dados_antes", sa.Text(), nullable=True),
        sa.Column("dados_depois", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_socios_historico_socio", "socios_historico", ["socio_id"], unique=False
    )
    op.create_index(
        "ix_socios_historico_alterado_por",
        "socios_historico",
        ["alterado_por"],
        unique=False,
    )
    op.create_index(
        "ix_socios_historico_created_at",
        "socios_historico",
        ["created_at"],
        unique=False,
    )


def _assert_sem_evidencia_nova() -> None:
    bind = op.get_bind()
    verificacoes = {
        "assinaturas multiparte/recusas": """
            SELECT COUNT(*)
              FROM signature_signers ss
              JOIN signature_requests sr ON sr.id = ss.signature_request_id
             WHERE ss.status = 'recusado'
                OR (ss.status = 'assinado' AND
                    (sr.assinado_por_user IS NULL OR ss.user_id <> sr.assinado_por_user))
        """,
        "histórico societário": "SELECT COUNT(*) FROM socios_historico",
        "meta de produtividade societária": (
            "SELECT COUNT(*) FROM socios WHERE meta_produtividade IS NOT NULL"
        ),
        "despesas recorrentes geradas": (
            "SELECT COUNT(*) FROM office_expenses WHERE recorrencia_origem_id IS NOT NULL"
        ),
        "prazos com nova trilha de cálculo": (
            "SELECT COUNT(*) FROM deadlines WHERE data_publicacao IS NOT NULL "
            "OR termo_inicial IS NOT NULL OR regime_calculo IS NOT NULL "
            "OR calculo_automatico = TRUE"
        ),
        "documentos publicados pelo novo fluxo": (
            "SELECT COUNT(*) FROM documents WHERE publicado_por IS NOT NULL"
        ),
    }
    usados = [
        nome
        for nome, sql in verificacoes.items()
        if int(bind.execute(sa.text(sql)).scalar() or 0) > 0
    ]
    if usados:
        raise RuntimeError(
            "Downgrade 143 recusado: há evidência operacional não representável "
            "com segurança no schema legado: "
            + ", ".join(usados)
            + ". Faça backup e forward-fix."
        )


def downgrade() -> None:
    _assert_sem_evidencia_nova()
    op.drop_index("ix_socios_historico_created_at", table_name="socios_historico")
    op.drop_index("ix_socios_historico_alterado_por", table_name="socios_historico")
    op.drop_index("ix_socios_historico_socio", table_name="socios_historico")
    op.drop_table("socios_historico")
    op.drop_column("socios", "meta_produtividade")
    op.drop_column("notas_fiscais_servico", "cancelamento_confirmado_em")
    op.drop_column("notas_fiscais_servico", "cancelamento_fiscal_confirmado")
    op.drop_column("notas_fiscais_servico", "cancelamento_tipo")
    op.drop_index("ix_signature_signers_status", table_name="signature_signers")
    op.drop_index("ix_signature_signers_user", table_name="signature_signers")
    op.drop_index("ix_signature_signers_request", table_name="signature_signers")
    op.drop_table("signature_signers")
    op.drop_index("ix_documents_publicado_portal", table_name="documents")
    op.drop_constraint(
        "fk_documents_publicado_por_users", "documents", type_="foreignkey"
    )
    op.drop_column("documents", "publicado_por")
    op.drop_column("documents", "publicado_em")
    op.drop_column("documents", "publicado_portal")
    op.drop_index(
        "ix_office_expenses_recorrencia_origem", table_name="office_expenses"
    )
    op.drop_constraint(
        "fk_office_expenses_recorrencia_origem",
        "office_expenses",
        type_="foreignkey",
    )
    op.drop_column("office_expenses", "recorrencia_origem_id")
    op.drop_index("ix_deadlines_regime_calculo", table_name="deadlines")
    op.drop_column("deadlines", "calculo_automatico")
    op.drop_column("deadlines", "regime_calculo")
    op.drop_column("deadlines", "termo_inicial")
    op.drop_column("deadlines", "data_publicacao")
