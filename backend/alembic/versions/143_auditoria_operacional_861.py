"""143 — auditoria operacional: prazos, financeiro, portal e assinaturas.

Migration PROVISÓRIA desta branch (Issue #861), criada sobre o head canônico
138. Os números 139–142 estão ocupados por PRs concorrentes ainda não
mesclados; este PR deve permanecer DRAFT e ser renumerado/reencadeado antes do
merge se qualquer um deles integrar a main.

Mudanças aditivas:
- deadlines: publicação/termo inicial/regime/rastro de cálculo;
- office_expenses: origem do template recorrente + unicidade por competência;
- documents: publicação externa explícita independente da confidencialidade;
- signature_signers: evidência individual para múltiplos signatários;
- NFSe: natureza/prova do cancelamento local x fiscal;
- socios: meta de produtividade persistida + histórico imutável de mutações.

Compatibilidade:
- documentos atualmente `normal` são backfillados como publicados, porque a
  migration 127 já transformou `normal` em escolha explícita de publicação;
- solicitações de assinatura legadas assinadas recebem apenas o signatário que
  efetivamente assinou; pendentes recebem os usuários ativos do portal;
- notas manuais canceladas são marcadas como cancelamento registral, não fiscal.

Rollback seguro: downgrade só é permitido enquanto os novos campos/tabelas não
contiverem evidência operacional criada após o upgrade. Depois do go-live, a
estratégia correta é forward-fix; apagar trilha de assinatura/societária/fiscal
seria juridicamente inadequado.

Revision ID: 143_auditoria_operacional_861
Revises: 138_consolida_fontes_ingestao
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "143_auditoria_operacional_861"
down_revision = "138_consolida_fontes_ingestao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Prazos: rastreabilidade jurídica do cálculo ──────────────────────
    op.add_column("deadlines", sa.Column("data_publicacao", sa.Date(), nullable=True))
    op.add_column("deadlines", sa.Column("termo_inicial", sa.Date(), nullable=True))
    op.add_column("deadlines", sa.Column("regime_calculo", sa.String(length=20), nullable=True))
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

    # ── 2. Recorrência: template -> lançamento, sem filhos virarem templates ─
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
    op.create_unique_constraint(
        "uq_office_expenses_origem_competencia",
        "office_expenses",
        ["recorrencia_origem_id", "competencia"],
    )

    # ── 3. Portal: classificação interna != autorização externa ─────────────
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
    # Preserva o estado efetivo da migration 127: hoje `normal` significa que
    # alguém reclassificou conscientemente o documento para exposição.
    op.execute(
        sa.text(
            """
            UPDATE documents
               SET publicado_portal = TRUE,
                   publicado_em = COALESCE(updated_at, created_at)
             WHERE deleted_at IS NULL
               AND confidencialidade::text = 'normal'
            """
        )
    )

    # ── 4. Assinaturas: evidência por signatário ─────────────────────────────
    signer_status = postgresql.ENUM(
        "pendente", "assinado", "recusado", name="signaturesignerstatus"
    )
    signer_status.create(op.get_bind(), checkfirst=True)
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
            "status",
            signer_status,
            nullable=False,
            server_default="pendente",
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

    # Legado já assinado: só há prova de UM usuário, portanto não inventar os
    # demais signatários. Copia exatamente a evidência disponível.
    op.execute(
        sa.text(
            """
            INSERT INTO signature_signers
                (id, signature_request_id, user_id, nome_snapshot,
                 email_snapshot, papel_snapshot, status, assinado_em, ip,
                 user_agent, created_at)
            SELECT gen_random_uuid()::text,
                   sr.id,
                   sr.assinado_por_user,
                   u.full_name,
                   u.email,
                   'cliente',
                   'assinado'::signaturesignerstatus,
                   sr.assinado_em,
                   sr.ip,
                   sr.user_agent,
                   sr.created_at
              FROM signature_requests sr
              JOIN users u ON u.id = sr.assinado_por_user
             WHERE sr.deleted_at IS NULL
               AND sr.status::text = 'assinado'
               AND sr.assinado_por_user IS NOT NULL
            ON CONFLICT (signature_request_id, user_id) DO NOTHING
            """
        )
    )
    # Legado pendente: recria a expectativa que a UI já anunciava — todos os
    # logins ativos do Portal vinculados ao cliente são signatários pendentes.
    op.execute(
        sa.text(
            """
            INSERT INTO signature_signers
                (id, signature_request_id, user_id, nome_snapshot,
                 email_snapshot, papel_snapshot, status, created_at)
            SELECT gen_random_uuid()::text,
                   sr.id,
                   u.id,
                   u.full_name,
                   u.email,
                   'cliente',
                   'pendente'::signaturesignerstatus,
                   sr.created_at
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
    )

    # ── 5. NFS-e: distinguir registro encerrado de cancelamento fiscal ──────
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
        sa.Column("cancelamento_confirmado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE notas_fiscais_servico
               SET cancelamento_tipo = 'registro_local',
                   cancelamento_fiscal_confirmado = FALSE
             WHERE status = 'cancelada' AND provider = 'manual'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE notas_fiscais_servico
               SET cancelamento_tipo = 'fiscal_provider',
                   cancelamento_fiscal_confirmado = TRUE,
                   cancelamento_confirmado_em = updated_at
             WHERE status = 'cancelada' AND provider <> 'manual'
            """
        )
    )

    # ── 6. Sociedade: persistência + trilha interna imutável ────────────────
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
        "signature_signers": "SELECT COUNT(*) FROM signature_signers",
        "socios_historico": "SELECT COUNT(*) FROM socios_historico",
        "office_expenses recorrentes geradas": (
            "SELECT COUNT(*) FROM office_expenses WHERE recorrencia_origem_id IS NOT NULL"
        ),
        "prazos com metadados de cálculo": (
            "SELECT COUNT(*) FROM deadlines WHERE data_publicacao IS NOT NULL "
            "OR termo_inicial IS NOT NULL OR regime_calculo IS NOT NULL OR calculo_automatico = TRUE"
        ),
        "documentos publicados pelo novo fluxo": (
            "SELECT COUNT(*) FROM documents WHERE publicado_por IS NOT NULL"
        ),
        "evidência nova de cancelamento NFSe": (
            "SELECT COUNT(*) FROM notas_fiscais_servico "
            "WHERE cancelamento_confirmado_em IS NOT NULL AND updated_at > created_at"
        ),
    }
    usados = [
        nome for nome, sql in verificacoes.items() if int(bind.execute(sa.text(sql)).scalar() or 0) > 0
    ]
    if usados:
        raise RuntimeError(
            "Downgrade 143 recusado: há evidência operacional nos novos campos/tabelas: "
            + ", ".join(usados)
            + ". Faça backup e forward-fix; não apague trilha jurídica/financeira."
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
    postgresql.ENUM(name="signaturesignerstatus").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_documents_publicado_portal", table_name="documents")
    op.drop_constraint("fk_documents_publicado_por_users", "documents", type_="foreignkey")
    op.drop_column("documents", "publicado_por")
    op.drop_column("documents", "publicado_em")
    op.drop_column("documents", "publicado_portal")

    op.drop_constraint(
        "uq_office_expenses_origem_competencia", "office_expenses", type_="unique"
    )
    op.drop_index("ix_office_expenses_recorrencia_origem", table_name="office_expenses")
    op.drop_constraint(
        "fk_office_expenses_recorrencia_origem", "office_expenses", type_="foreignkey"
    )
    op.drop_column("office_expenses", "recorrencia_origem_id")

    op.drop_index("ix_deadlines_regime_calculo", table_name="deadlines")
    op.drop_column("deadlines", "calculo_automatico")
    op.drop_column("deadlines", "regime_calculo")
    op.drop_column("deadlines", "termo_inicial")
    op.drop_column("deadlines", "data_publicacao")
